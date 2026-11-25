"""실행 관리자: 대화 메시지를 에이전트 실행으로 바꾸고, 이벤트를 저장·방송하고, 승인을 중계한다.

흐름: send() → 라우팅(대상·멘션) → 에이전트별 assistant 메시지(pending) 생성 → 백그라운드 작업에서
RunRequest를 만들어 런타임 실행 → 이벤트를 ChatMessage/RuntimeSession/Agent.status에 반영하고 EventBus로 방송.
"""

from __future__ import annotations

import asyncio
import contextlib
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from ai_org.config import Settings
from ai_org.models import (
    ActivityEvent,
    Agent,
    AgentThread,
    Approval,
    Attachment,
    ChatMessage,
    Conversation,
    Department,
    Organization,
    Project,
    RuntimeSession,
    Task,
)
from ai_org.runtime.activity import classify, target_of
from ai_org.runtime.base import AgentRuntime, PermissionDecision, RunRequest
from ai_org.schemas import AgentPermissions
from ai_org.services import policy
from ai_org.services.bus import EventBus
from ai_org.services.prompting import ContextLines, system_append, user_prompt

GITHUB_REPO = re.compile(r"^[\w.-]+/[\w.-]+$")
MAX_TASK_RESULT = 4000


class RouteError(ValueError):
    pass


@dataclass
class Route:
    agent: Agent
    scope: str  # org | team | agent
    team: Department | None = None
    broadcast: bool = False


@dataclass
class ActiveRun:
    message_id: str
    conversation_id: str
    agent_id: str
    handle: Any = None
    approvals: set[str] = field(default_factory=set)
    task: asyncio.Task[None] | None = None


def utcnow() -> datetime:
    return datetime.now(UTC)


def team_lead(db: Session, dept: Department) -> Agent | None:
    """부서 대표: 상위 관리자가 부서 밖에 있는 첫 구성원."""
    members = list(
        db.scalars(
            select(Agent)
            .where(Agent.department_id == dept.id, Agent.enabled.is_(True))
            .order_by(Agent.created_at)
        )
    )
    ids = {m.id for m in members}
    for m in members:
        if m.reports_to_id not in ids:
            return m
    return members[0] if members else None


def org_lead(db: Session, org_id: str) -> Agent | None:
    return db.scalar(
        select(Agent).where(Agent.organization_id == org_id, Agent.is_lead.is_(True), Agent.enabled.is_(True))
    )


def resolve_routes(db: Session, conv: Conversation, mention_ids: list[str], mention_all: bool) -> list[Route]:
    if mention_all:
        lead = org_lead(db, conv.organization_id)
        if lead is None:
            raise RouteError("조직에 활성화된 CEO가 없습니다.")
        return [Route(lead, "org", broadcast=True)]
    if mention_ids:
        routes = []
        for agent_id in dict.fromkeys(mention_ids):
            agent = db.get(Agent, agent_id)
            if agent is None or agent.organization_id != conv.organization_id:
                raise RouteError("멘션한 에이전트가 이 조직에 없습니다.")
            if not agent.enabled:
                raise RouteError(f"'{agent.name}'은(는) 비활성화되어 있습니다.")
            routes.append(Route(agent, "agent"))
        return routes
    if conv.target_kind == "agent" and conv.target_id:
        agent = db.get(Agent, conv.target_id)
        if agent is None or agent.organization_id != conv.organization_id or not agent.enabled:
            raise RouteError("대화 대상 에이전트를 사용할 수 없습니다.")
        return [Route(agent, "agent")]
    if conv.target_kind == "team" and conv.target_id:
        dept = db.get(Department, conv.target_id)
        if dept is None or dept.organization_id != conv.organization_id:
            raise RouteError("대화 대상 팀이 없습니다.")
        lead = team_lead(db, dept)
        if lead is None:
            raise RouteError(f"'{dept.name}' 팀에 구성원이 없습니다.")
        return [Route(lead, "team", team=dept)]
    lead = org_lead(db, conv.organization_id)
    if lead is None:
        raise RouteError("조직에 활성화된 CEO가 없습니다.")
    return [Route(lead, "org")]


def validate_context(db: Session, conv: Conversation, items: list[dict[str, Any]]) -> ContextLines:
    """컨텍스트 항목을 검증해 프롬프트 줄로 바꾼다. 허용 범위 밖은 예외."""
    ctx = ContextLines()
    project = db.get(Project, conv.project_id) if conv.project_id else None
    if project is not None:
        ctx.project = project.path
    root = Path(project.path).resolve() if project else None
    for item in items:
        kind, ref = item.get("kind"), str(item.get("ref", ""))
        if kind == "path":
            if root is None:
                raise RouteError("경로 컨텍스트는 프로젝트를 연결한 대화에서만 쓸 수 있습니다.")
            path = (root / ref).resolve() if not Path(ref).is_absolute() else Path(ref).resolve()
            if not policy.within(path, [root]) or not path.exists():
                raise RouteError(f"프로젝트 밖이거나 없는 경로입니다: {ref}")
            ctx.paths.append(str(path))
        elif kind == "agent":
            agent = db.get(Agent, ref)
            if agent is None or agent.organization_id != conv.organization_id:
                raise RouteError("컨텍스트 에이전트가 이 조직에 없습니다.")
            ctx.agents.append(f"{agent.name}({agent.title})" if agent.title else agent.name)
        elif kind == "task":
            task = db.get(Task, ref)
            if task is None or task.organization_id != conv.organization_id:
                raise RouteError("컨텍스트 작업이 이 조직에 없습니다.")
            ctx.tasks.append((task.title, (task.result or "(결과 없음)")[:MAX_TASK_RESULT]))
        elif kind == "github":
            if not GITHUB_REPO.match(ref):
                raise RouteError("GitHub 저장소는 owner/repo 형식이어야 합니다.")
            ctx.github.append(ref)
        elif kind == "capability":
            ctx.capabilities.append(ref[:120])
        else:
            raise RouteError(f"알 수 없는 컨텍스트 종류: {kind}")
    return ctx


class RunManager:
    def __init__(
        self,
        settings: Settings,
        factory: sessionmaker[Session],
        bus: EventBus,
        runtime_for: Callable[[str], AgentRuntime],
    ) -> None:
        self.settings = settings
        self.factory = factory
        self.bus = bus
        self.runtime_for = runtime_for
        self.runs: dict[str, ActiveRun] = {}
        self.pending: dict[str, asyncio.Future[PermissionDecision]] = {}
        self.limit = asyncio.Semaphore(settings.max_concurrent_runs)

    # ── 시작 시 복구 ───────────────────────────────────────────────────────

    def recover(self) -> None:
        """이전 프로세스가 비정상 종료되어 남은 '진행 중' 상태를 정리한다."""
        with self.factory() as db:
            for msg in db.scalars(
                select(ChatMessage).where(ChatMessage.status.in_(("pending", "streaming")))
            ):
                msg.status = "interrupted"
                msg.error = "서버가 재시작되어 실행이 중단되었습니다."
            for rs in db.scalars(
                select(RuntimeSession).where(RuntimeSession.state.in_(("starting", "running")))
            ):
                rs.state, rs.ended_at = "interrupted", utcnow()
            for ap in db.scalars(select(Approval).where(Approval.status == "pending")):
                ap.status, ap.decided_at = "expired", utcnow()
            for agent in db.scalars(select(Agent).where(Agent.status != "idle")):
                agent.status = "idle"
            for task in db.scalars(select(Task).where(Task.status == "running")):
                task.status = "failed"
                task.result = "서버 재시작으로 중단됨"
            db.commit()

    # ── 실행 ───────────────────────────────────────────────────────────────

    def is_busy(self, conversation_id: str) -> bool:
        return any(r.conversation_id == conversation_id for r in self.runs.values())

    def launch(
        self,
        db: Session,
        conv: Conversation,
        route: Route,
        prompt: str,
        attachments: list[Attachment],
        task_id: str | None = None,
    ) -> ChatMessage:
        msg = ChatMessage(
            conversation_id=conv.id,
            role="assistant",
            agent_id=route.agent.id,
            status="pending",
            task_id=task_id,
        )
        db.add(msg)
        db.commit()
        run = ActiveRun(message_id=msg.id, conversation_id=conv.id, agent_id=route.agent.id)
        self.runs[msg.id] = run
        request = self._build_request(db, conv, route, prompt, attachments)
        run.task = asyncio.create_task(self._execute(run, request, route.agent.runtime))
        self.bus.publish(
            "message.created",
            conversation_id=conv.id,
            message=_message_json(msg),
        )
        return msg

    def _cwd(self, db: Session, conv: Conversation, agent: Agent) -> Path:
        project = db.get(Project, conv.project_id) if conv.project_id else None
        if project is not None and Path(project.path).is_dir():
            return Path(project.path)
        workspace = self.settings.home / "workspaces" / agent.organization_id / agent.id
        workspace.mkdir(parents=True, exist_ok=True, mode=0o700)
        return workspace

    def _build_request(
        self, db: Session, conv: Conversation, route: Route, prompt: str, attachments: list[Attachment]
    ) -> RunRequest:
        agent = route.agent
        org = db.get(Organization, conv.organization_id)
        assert org is not None
        agents = list(
            db.scalars(select(Agent).where(Agent.organization_id == org.id).order_by(Agent.created_at))
        )
        depts = list(db.scalars(select(Department).where(Department.organization_id == org.id)))
        ctx = validate_context(db, conv, conv.context or [])
        perms = AgentPermissions.model_validate(agent.permissions or {})
        cwd = self._cwd(db, conv, agent)
        thread = db.scalar(
            select(AgentThread).where(
                AgentThread.conversation_id == conv.id, AgentThread.agent_id == agent.id
            )
        )
        resume = thread.session_id if thread is not None and thread.cwd == str(cwd) else None
        skills = tuple(cap.split(":")[-1] for cap in agent.allowed_skills)
        return RunRequest(
            agent_id=agent.id,
            prompt=user_prompt(prompt, ctx, attachments, broadcast=route.broadcast),
            cwd=cwd,
            system_prompt_append=system_append(org, agent, agents, depts, route.scope, route.team),
            model=agent.model,
            disallowed_tools=policy.disallowed_tools(perms),
            permission_mode=perms.permission_mode,
            add_dirs=tuple(sorted({Path(a.stored_path).parent for a in attachments})),
            skills=skills,
            resume_session_id=resume,
            max_turns=self.settings.max_turns,
            approval_timeout_s=self.settings.approval_timeout_s,
        )

    def _set_agent_status(self, agent_id: str, status: str, detail: str = "") -> None:
        with self.factory() as db:
            agent = db.get(Agent, agent_id)
            if agent is None or agent.status == status:
                return
            agent.status = status
            db.commit()
            self.bus.publish(
                "agent.status",
                organization_id=agent.organization_id,
                agent_id=agent_id,
                status=status,
                detail=detail,
            )

    async def _execute(self, run: ActiveRun, request: RunRequest, runtime_id: str) -> None:
        text_parts: list[str] = []
        streamed: list[str] = []
        activity: list[dict[str, Any]] = []
        session_row_id: str | None = None
        final_status, error = "done", None
        result: dict[str, Any] = {}
        try:
            async with self.limit:
                with self.factory() as db:
                    msg = db.get(ChatMessage, run.message_id)
                    if msg is None:
                        return
                    msg.status = "streaming"
                    rs = RuntimeSession(
                        agent_id=run.agent_id, task_id=msg.task_id, cwd=str(request.cwd), state="running"
                    )
                    db.add(rs)
                    db.commit()
                    session_row_id = rs.id
                self.bus.publish(
                    "message.status",
                    conversation_id=run.conversation_id,
                    message_id=run.message_id,
                    status="streaming",
                )
                self._set_agent_status(run.agent_id, "thinking")
                perms = self._perms(run.agent_id)
                roots = [request.cwd, *request.add_dirs]

                async def on_permission(tool: str, tool_input: dict[str, Any]) -> PermissionDecision:
                    return await self._permission(run, perms, roots, tool, tool_input, activity)

                runtime = self.runtime_for(runtime_id)
                handle = runtime.start(request, on_permission)
                run.handle = handle
                async for ev in handle.events():
                    if ev.type == "session.started":
                        sid = ev.data.get("session_id")
                        self._record_session(run, session_row_id, sid, request.cwd)
                    elif ev.type == "message.delta":
                        streamed.append(ev.data["text"])
                        self.bus.publish(
                            "message.delta",
                            conversation_id=run.conversation_id,
                            message_id=run.message_id,
                            text=ev.data["text"],
                        )
                    elif ev.type == "message":
                        text_parts.append(ev.data["text"])
                    elif ev.type == "tool.started":
                        tool_input = ev.data.get("input") or {}
                        entry = {
                            "id": ev.data["id"],
                            "tool": ev.data["tool"],
                            "activity": classify(ev.data["tool"], tool_input),
                            "target": target_of(ev.data["tool"], tool_input),
                            "status": "running",
                            "subagent": bool(ev.data.get("subagent")),
                            "at": utcnow().isoformat(),
                        }
                        activity.append(entry)
                        self._set_agent_status(run.agent_id, "working", entry["activity"])
                        self._publish_activity(run, entry)
                    elif ev.type in ("tool.completed", "tool.failed"):
                        for entry in activity:
                            if entry["id"] == ev.data["id"] and entry["status"] == "running":
                                entry["status"] = "done" if ev.type == "tool.completed" else "failed"
                                self._publish_activity(run, entry)
                        if not any(e["status"] == "running" for e in activity):
                            self._set_agent_status(run.agent_id, "thinking")
                    elif ev.type == "turn.completed":
                        result = ev.data
                        if ev.data.get("session_id"):
                            self._record_session(run, session_row_id, ev.data["session_id"], request.cwd)
                        if ev.data.get("interrupted"):
                            final_status = "interrupted"
                        elif ev.data.get("is_error"):
                            final_status, error = "error", f"실행 오류({ev.data.get('subtype')})"
                    elif ev.type == "error":
                        final_status, error = "error", ev.data.get("message", "알 수 없는 오류")
        except asyncio.CancelledError:
            final_status, error = "interrupted", "중지됨"
        except Exception as exc:
            final_status, error = "error", f"{type(exc).__name__}: {exc}"[:500]
        finally:
            content = "\n\n".join(text_parts) if text_parts else "".join(streamed)
            for entry in activity:
                if entry["status"] == "running":
                    entry["status"] = "cancelled" if final_status != "done" else "done"
            self._finish(run, session_row_id, final_status, error, content, activity, result)
            self.runs.pop(run.message_id, None)

    def _perms(self, agent_id: str) -> AgentPermissions:
        with self.factory() as db:
            agent = db.get(Agent, agent_id)
            return AgentPermissions.model_validate(agent.permissions if agent else {})

    def _record_session(self, run: ActiveRun, row_id: str | None, sid: str | None, cwd: Path) -> None:
        if not sid:
            return
        with self.factory() as db:
            if row_id and (rs := db.get(RuntimeSession, row_id)) is not None:
                rs.external_session_id = sid
            msg = db.get(ChatMessage, run.message_id)
            if msg is not None:
                msg.session_id = sid
            thread = db.scalar(
                select(AgentThread).where(
                    AgentThread.conversation_id == run.conversation_id, AgentThread.agent_id == run.agent_id
                )
            )
            if thread is None:
                db.add(
                    AgentThread(
                        conversation_id=run.conversation_id,
                        agent_id=run.agent_id,
                        session_id=sid,
                        cwd=str(cwd),
                    )
                )
            else:
                thread.session_id, thread.cwd = sid, str(cwd)
            db.commit()

    def _publish_activity(self, run: ActiveRun, entry: dict[str, Any]) -> None:
        self.bus.publish(
            "run.activity",
            conversation_id=run.conversation_id,
            message_id=run.message_id,
            agent_id=run.agent_id,
            entry=entry,
        )

    def _finish(
        self,
        run: ActiveRun,
        session_row_id: str | None,
        status: str,
        error: str | None,
        content: str,
        activity: list[dict[str, Any]],
        result: dict[str, Any],
    ) -> None:
        for approval_id in list(run.approvals):
            self._resolve(
                approval_id, PermissionDecision(False, "실행이 끝났습니다."), status_label="expired"
            )
        with self.factory() as db:
            msg = db.get(ChatMessage, run.message_id)
            if msg is None:
                return
            msg.status, msg.error, msg.content, msg.activity = status, error, content, activity
            msg.cost_usd = result.get("cost_usd")
            msg.duration_ms = result.get("duration_ms")
            if session_row_id and (rs := db.get(RuntimeSession, session_row_id)) is not None:
                rs.state = {"done": "ended", "interrupted": "interrupted"}.get(status, "failed")
                rs.cost_usd, rs.ended_at = result.get("cost_usd"), utcnow()
            agent = db.get(Agent, run.agent_id)
            org_id = agent.organization_id if agent else None
            if msg.task_id and (task := db.get(Task, msg.task_id)) is not None:
                task.status = {"done": "done", "interrupted": "cancelled"}.get(status, "failed")
                task.result = (content or error or "")[:MAX_TASK_RESULT]
                self.bus.publish(
                    "task.updated", organization_id=task.organization_id, task_id=task.id, status=task.status
                )
            if agent is not None:
                label = {"done": "응답 완료", "interrupted": "중지됨"}.get(status, "실행 실패")
                db.add(
                    ActivityEvent(
                        organization_id=org_id,
                        agent_id=agent.id,
                        kind=f"run.{status}",
                        summary=f"{agent.name}: {label}",
                    )
                )
            conv = db.get(Conversation, run.conversation_id)
            if conv is not None:
                conv.updated_at = utcnow()
            db.commit()
            payload = _message_json(msg)
        self.bus.publish("message.completed", conversation_id=run.conversation_id, message=payload)
        next_status = {"done": "completed", "interrupted": "idle"}.get(status, "failed")
        self._set_agent_status(run.agent_id, next_status)

    # ── 승인 ───────────────────────────────────────────────────────────────

    async def _permission(
        self,
        run: ActiveRun,
        perms: AgentPermissions,
        roots: list[Path],
        tool: str,
        tool_input: dict[str, Any],
        activity: list[dict[str, Any]],
    ) -> PermissionDecision:
        verdict = policy.decide(perms, tool, tool_input, roots)
        if verdict.action == "allow":
            return PermissionDecision(True)
        if verdict.action == "deny":
            self.bus.publish(
                "run.denied",
                conversation_id=run.conversation_id,
                message_id=run.message_id,
                agent_id=run.agent_id,
                tool=tool,
                reason=verdict.reason,
            )
            return PermissionDecision(False, verdict.reason)
        target = target_of(tool, tool_input, limit=300)
        with self.factory() as db:
            agent = db.get(Agent, run.agent_id)
            assert agent is not None
            approval = Approval(
                organization_id=agent.organization_id,
                agent_id=agent.id,
                kind="tool",
                summary=f"{tool}: {target}" if target else tool,
                detail={
                    "tool": tool,
                    "target": target,
                    "group": verdict.group,
                    "reason": verdict.reason,
                    "conversation_id": run.conversation_id,
                    "message_id": run.message_id,
                },
            )
            db.add(approval)
            db.commit()
            approval_id, org_id, agent_name = approval.id, agent.organization_id, agent.name
        future: asyncio.Future[PermissionDecision] = asyncio.get_running_loop().create_future()
        self.pending[approval_id] = future
        run.approvals.add(approval_id)
        self._set_agent_status(run.agent_id, "waiting", tool)
        self.bus.publish(
            "approval.requested",
            organization_id=org_id,
            conversation_id=run.conversation_id,
            approval={
                "id": approval_id,
                "agent_id": run.agent_id,
                "agent_name": agent_name,
                "tool": tool,
                "target": target,
                "group": verdict.group,
                "reason": verdict.reason,
                "message_id": run.message_id,
            },
        )
        try:
            decision = await asyncio.wait_for(future, timeout=self.settings.approval_timeout_s)
        except TimeoutError:
            self._resolve(
                approval_id, PermissionDecision(False, "승인 대기 시간이 지났습니다."), status_label="expired"
            )
            decision = PermissionDecision(False, "승인 대기 시간이 지났습니다.")
        finally:
            run.approvals.discard(approval_id)
            self.pending.pop(approval_id, None)
        self._set_agent_status(run.agent_id, "working" if decision.allow else "thinking")
        return decision

    def decide(self, approval_id: str, allow: bool) -> bool:
        if approval_id not in self.pending:
            return False
        message = "" if allow else "사용자가 거부했습니다."
        self._resolve(
            approval_id, PermissionDecision(allow, message), status_label="approved" if allow else "denied"
        )
        return True

    def _resolve(self, approval_id: str, decision: PermissionDecision, status_label: str) -> None:
        future = self.pending.get(approval_id)
        if future is not None and not future.done():
            future.set_result(decision)
        with self.factory() as db:
            approval = db.get(Approval, approval_id)
            if approval is not None and approval.status == "pending":
                approval.status, approval.decided_at = status_label, utcnow()
                db.commit()
                self.bus.publish(
                    "approval.resolved",
                    organization_id=approval.organization_id,
                    approval_id=approval_id,
                    status=status_label,
                )

    # ── 중지 ───────────────────────────────────────────────────────────────

    async def stop(self, conversation_id: str | None = None, organization_id: str | None = None) -> int:
        targets = [
            r
            for r in self.runs.values()
            if (conversation_id is None or r.conversation_id == conversation_id)
            and (organization_id is None or self._org_of(r.agent_id) == organization_id)
        ]
        for run in targets:
            for approval_id in list(run.approvals):
                self._resolve(
                    approval_id, PermissionDecision(False, "사용자가 중지했습니다."), status_label="denied"
                )
            if run.handle is not None:
                with contextlib.suppress(Exception):
                    await asyncio.wait_for(run.handle.interrupt(), timeout=5)
            elif run.task is not None:
                run.task.cancel()
        return len(targets)

    def _org_of(self, agent_id: str) -> str | None:
        with self.factory() as db:
            agent = db.get(Agent, agent_id)
            return agent.organization_id if agent else None

    async def shutdown(self) -> None:
        await self.stop()
        tasks = [r.task for r in self.runs.values() if r.task is not None]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


def _message_json(msg: ChatMessage) -> dict[str, Any]:
    return {
        "id": msg.id,
        "conversation_id": msg.conversation_id,
        "role": msg.role,
        "agent_id": msg.agent_id,
        "content": msg.content,
        "data": msg.data or {},
        "activity": msg.activity or [],
        "status": msg.status,
        "error": msg.error,
        "cost_usd": msg.cost_usd,
        "duration_ms": msg.duration_ms,
        "task_id": msg.task_id,
        "created_at": (msg.created_at or utcnow()).isoformat(),
    }


message_json = _message_json
