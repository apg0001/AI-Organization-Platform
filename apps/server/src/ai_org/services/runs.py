"""실행 관리자: 대화 메시지를 에이전트 실행으로 바꾸고, 이벤트를 저장·방송하고, 승인을 중계한다.

흐름: send() → 라우팅(대상·멘션) → 에이전트별 assistant 메시지(pending) 생성 → 백그라운드 작업에서
RunRequest를 만들어 런타임 실행 → 이벤트를 ChatMessage/RuntimeSession/Agent.status에 반영하고 EventBus로 방송.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import re
from collections.abc import AsyncIterator, Callable
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
    Collaboration,
    Conversation,
    Department,
    Organization,
    Project,
    RuntimeSession,
    Task,
)
from ai_org.runtime.activity import classify, target_of
from ai_org.runtime.base import AgentRuntime, OrgTool, PermissionDecision, RunRequest
from ai_org.schemas import AgentPermissions
from ai_org.services import policy
from ai_org.services.bus import EventBus
from ai_org.services.capabilities import resolve_mcp_servers, resolve_plugin_paths
from ai_org.services.prompting import ContextLines, system_append, user_prompt

GITHUB_REPO = re.compile(r"^[\w.-]+/[\w.-]+$")
MAX_TASK_RESULT = 4000
MAX_REPORT = 6000
MAX_DELEGATION_DEPTH = 3
MAX_PLAN_TASKS = 12
MAX_REVISIONS = 2
PLAN_REPORT = 1500
DEP_EXCERPT = 2000
APPROVED = re.compile(r"^\s*\**\s*\[승인\]")
PLAN_STATUS = {
    "done": "완료",
    "failed": "실패",
    "cancelled": "취소",
    "review": "검토 미승인",
    "interrupted": "중지",
}
PLAN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "tasks": {
            "type": "array",
            "maxItems": 12,
            "items": {
                "type": "object",
                "properties": {
                    "key": {"type": "string", "description": "계획 안에서 쓰는 짧은 식별자"},
                    "assignee": {"type": "string", "description": "담당 구성원 이름"},
                    "title": {"type": "string"},
                    "brief": {"type": "string", "description": "목표·범위·결과물 형식"},
                    "depends_on": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "먼저 끝나야 하는 작업 key",
                    },
                    "review_by": {"type": "string", "description": "결과를 검토할 구성원 이름(선택)"},
                },
                "required": ["key", "assignee", "title", "brief"],
            },
        }
    },
    "required": ["tasks"],
}


@dataclass
class PlanItem:
    key: str
    assignee_id: str
    assignee_name: str
    title: str
    brief: str
    depends_on: list[str]
    reviewer_id: str | None
    task_id: str = ""


def _find_cycle(items: dict[str, PlanItem]) -> list[str]:
    state: dict[str, int] = {}
    stack: list[str] = []

    def visit(key: str) -> list[str]:
        state[key] = 1
        stack.append(key)
        for dep in items[key].depends_on:
            if state.get(dep) == 1:
                return [*stack[stack.index(dep) :], dep]
            if state.get(dep) is None and (found := visit(dep)):
                return found
        stack.pop()
        state[key] = 2
        return []

    for key in items:
        if key not in state and (found := visit(key)):
            return found
    return []


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
    task_id: str | None = None
    # 위임 체인(이 실행에 이르기까지 위임한 에이전트들). 순환·깊이 제한에 쓴다.
    chain: tuple[str, ...] = ()


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


def delegation_targets(db: Session, agent: Agent) -> list[Agent]:
    """위임·검토 요청 가능한 대상(활성만).

    보고 트리의 모든 하위 구성원 + 이 에이전트가 협업 관계로 연결한 대상.
    """
    members = list(db.scalars(select(Agent).where(Agent.organization_id == agent.organization_id)))
    reports: dict[str, list[Agent]] = {}
    for m in members:
        if m.reports_to_id:
            reports.setdefault(m.reports_to_id, []).append(m)
    found: dict[str, Agent] = {}
    stack = list(reports.get(agent.id, []))
    while stack:
        m = stack.pop()
        if m.id not in found:
            found[m.id] = m
            stack.extend(reports.get(m.id, []))
    collab_targets = db.scalars(
        select(Collaboration.target_agent_id).where(Collaboration.source_agent_id == agent.id)
    )
    by_id = {m.id: m for m in members}
    for target_id in collab_targets:
        if target_id in by_id:
            found.setdefault(target_id, by_id[target_id])
    return [m for m in members if m.id in found and m.enabled and m.id != agent.id]


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
        chain: tuple[str, ...] = (),
        delegated_by: str | None = None,
    ) -> ChatMessage:
        msg = ChatMessage(
            conversation_id=conv.id,
            role="assistant",
            agent_id=route.agent.id,
            status="pending",
            task_id=task_id,
            data={"delegated_by": delegated_by} if delegated_by else {},
        )
        db.add(msg)
        db.commit()
        run = ActiveRun(
            message_id=msg.id, conversation_id=conv.id, agent_id=route.agent.id, task_id=task_id, chain=chain
        )
        self.runs[msg.id] = run
        request = self._build_request(db, conv, route, prompt, attachments, run)
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
        self,
        db: Session,
        conv: Conversation,
        route: Route,
        prompt: str,
        attachments: list[Attachment],
        run: ActiveRun | None = None,
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
        project_paths = list(db.scalars(select(Project.path)))
        can_delegate = perms.can_delegate and run is not None and len(run.chain) < MAX_DELEGATION_DEPTH
        delegates = delegation_targets(db, agent) if can_delegate else []
        org_tools = self._org_tools(run, conv.id) if run is not None and delegates else ()
        mcp_servers = resolve_mcp_servers(self.settings.claude_home, project_paths, agent.allowed_mcp_servers)
        plugin_paths = tuple(resolve_plugin_paths(self.settings.claude_home, agent.allowed_plugins))
        return RunRequest(
            agent_id=agent.id,
            prompt=user_prompt(prompt, ctx, attachments, broadcast=route.broadcast),
            cwd=cwd,
            system_prompt_append=system_append(org, agent, agents, depts, route.scope, route.team, delegates),
            model=agent.model,
            disallowed_tools=policy.disallowed_tools(perms),
            permission_mode=perms.permission_mode,
            add_dirs=tuple(sorted({Path(a.stored_path).parent for a in attachments})),
            skills=skills,
            resume_session_id=resume,
            max_turns=self.settings.max_turns,
            approval_timeout_s=self.settings.approval_timeout_s,
            mcp_servers=mcp_servers,
            plugin_paths=plugin_paths,
            org_tools=org_tools,
        )

    # ── 위임(Phase 5) ──────────────────────────────────────────────────────

    def _org_tools(self, run: ActiveRun, conversation_id: str) -> tuple[OrgTool, ...]:
        async def delegate(args: dict[str, Any]) -> str:
            return await self._delegate(run, conversation_id, "delegated", args)

        async def review(args: dict[str, Any]) -> str:
            return await self._delegate(run, conversation_id, "review", args)

        async def plan(args: dict[str, Any]) -> str:
            return await self._run_plan(run, conversation_id, args)

        return (
            OrgTool(
                "delegate_task",
                "조직의 하위 구성원 또는 협업 대상에게 업무를 위임하고, 그 구성원이 끝낸 결과 보고를 받는다. "
                "assignee는 구성원 이름, title은 짧은 작업 제목, "
                "brief는 목표·범위·결과물 형식을 담은 지시다. "
                "여러 구성원에게 동시에 위임하려면 이 도구를 여러 번 호출한다.",
                {"assignee": str, "title": str, "brief": str},
                delegate,
            ),
            OrgTool(
                "request_review",
                "하위 구성원 또는 협업 대상에게 결과물 검토를 요청하고 검토 의견을 받는다. "
                "content에 검토할 내용과 관점을 적는다.",
                {"reviewer": str, "content": str},
                review,
            ),
            OrgTool(
                "run_plan",
                "여러 단계로 된 업무를 작업 계획으로 한 번에 맡긴다. "
                "플랫폼이 선행 작업(depends_on) 순서를 지켜 실행하고, 독립 작업은 함께 진행하며, "
                "선행 작업 결과를 뒤 작업 지시에 붙여 준다. "
                "review_by를 주면 그 구성원이 결과를 검토하고, "
                "수정 요청이면 사유를 붙여 최대 2회 재작업한다. "
                "모든 작업이 끝나면 작업별 결과 보고를 돌려준다.",
                PLAN_SCHEMA,
                plan,
            ),
        )

    @contextlib.asynccontextmanager
    async def _slot_released(self) -> AsyncIterator[None]:
        """위임 결과를 기다리는 동안 동시 실행 슬롯을 내놓는다(위임받은 실행이 슬롯을 얻게 — 교착 방지)."""
        self.limit.release()
        try:
            yield
        finally:
            await asyncio.shield(self.limit.acquire())

    def _start_child(
        self,
        run: ActiveRun,
        conversation_id: str,
        target_id: str,
        header: str,
        brief: str,
        task_id: str,
        kind: str,
    ) -> str:
        """위임받은 에이전트를 같은 대화에서 실행한다. 메시지 ID를 돌려준다."""
        with self.factory() as db:
            conv = db.get(Conversation, conversation_id)
            target = db.get(Agent, target_id)
            assert conv is not None and target is not None
            child_msg = self.launch(
                db,
                conv,
                Route(target, "agent"),
                header + brief,
                [],
                task_id=task_id,
                chain=(*run.chain, run.agent_id),
                delegated_by=run.agent_id,
            )
            org_id = target.organization_id
        self.bus.publish(
            "task.delegated",
            organization_id=org_id,
            conversation_id=conversation_id,
            from_agent_id=run.agent_id,
            to_agent_id=target_id,
            task_id=task_id,
            kind=kind,
        )
        return child_msg.id

    async def _wait_child(self, message_id: str, task_id: str) -> tuple[str, str]:
        child = self.runs.get(message_id)
        if child is not None and child.task is not None:
            await asyncio.shield(child.task)
        with self.factory() as db:
            done = db.get(ChatMessage, message_id)
            finished = db.get(Task, task_id)
            body = (done.content or done.error or "(내용 없음)") if done else "(결과를 찾지 못함)"
            return (finished.status if finished else "unknown"), body

    async def _wait_agent_free(self, conversation_id: str, agent_id: str) -> None:
        while any(
            r.conversation_id == conversation_id and r.agent_id == agent_id for r in self.runs.values()
        ):
            await asyncio.sleep(0.2)

    def _new_task(
        self,
        db: Session,
        me: Agent,
        conv: Conversation,
        target: Agent,
        title: str,
        brief: str,
        parent_id: str | None,
        status: str = "running",
    ) -> Task:
        task = Task(
            organization_id=me.organization_id,
            project_id=conv.project_id,
            parent_id=parent_id,
            assignee_id=target.id,
            requested_by_id=me.id,
            title=title[:200],
            brief=brief,
            status=status,
        )
        db.add(task)
        db.flush()
        return task

    async def _delegate(self, run: ActiveRun, conversation_id: str, kind: str, args: dict[str, Any]) -> str:
        name = str(args.get("assignee") or args.get("reviewer") or "").strip().lstrip("@")
        brief = str(args.get("brief") or args.get("content") or "").strip()
        title = str(args.get("title") or "").strip() or (brief.splitlines()[0] if brief else "")
        if kind == "review":
            title = f"검토: {title}"
        with self.factory() as db:
            me = db.get(Agent, run.agent_id)
            conv = db.get(Conversation, conversation_id)
            if me is None or conv is None:
                return "위임할 수 없습니다: 실행 정보를 찾지 못했습니다."
            target, problem = self._check_target(db, run, me, name)
            if target is None:
                return problem
            if not brief:
                return "brief(업무 지시)가 비어 있습니다."
            if any(
                r.conversation_id == conversation_id and r.agent_id == target.id for r in self.runs.values()
            ):
                return f"'{target.name}'은(는) 이 대화에서 이미 작업 중입니다. 끝난 뒤 다시 요청하세요."
            task = self._new_task(db, me, conv, target, title, brief, run.task_id)
            verb = "검토 요청" if kind == "review" else "위임"
            db.add(
                ActivityEvent(
                    organization_id=me.organization_id,
                    agent_id=me.id,
                    kind=f"task.{kind}",
                    summary=f"{me.name} → {target.name} {verb}: {task.title}",
                )
            )
            db.commit()
            header = self._header(me, verb, task.title)
            task_id, target_id, target_name = task.id, target.id, target.name
        message_id = self._start_child(run, conversation_id, target_id, header, brief, task_id, kind)
        async with self._slot_released():
            status, body = await self._wait_child(message_id, task_id)
        return f"[{target_name}의 보고 — 작업 상태: {status}]\n{body[:MAX_REPORT]}"

    @staticmethod
    def _header(me: Agent, verb: str, title: str) -> str:
        return (
            f"[{me.name}({me.title})의 {verb}] 아래 업무를 처리하고, "
            f"결과를 {me.name}에게 보고하는 형식으로 정리하세요.\n"
            f"작업: {title}\n\n"
        )

    @staticmethod
    def _check_target(db: Session, run: ActiveRun, me: Agent, name: str) -> tuple[Agent | None, str]:
        targets = delegation_targets(db, me)
        target = next((a for a in targets if a.name == name.strip().lstrip("@")), None)
        if target is None:
            options = ", ".join(a.name for a in targets) or "없음"
            return (
                None,
                f"'{name}'에게는 위임할 수 없습니다(하위 구성원·협업 대상만 가능). 가능한 대상: {options}",
            )
        if target.id in run.chain:
            return None, f"'{target.name}'은(는) 이 업무를 위임한 쪽이라 다시 위임할 수 없습니다(위임 순환)."
        return target, ""

    # ── 작업 계획(run_plan) ────────────────────────────────────────────────

    async def _run_plan(self, run: ActiveRun, conversation_id: str, args: dict[str, Any]) -> str:
        raw = args.get("tasks")
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except json.JSONDecodeError:
                return "tasks는 작업 목록(JSON 배열)이어야 합니다."
        if not isinstance(raw, list) or not raw:
            return "tasks에 작업이 하나 이상 있어야 합니다."
        if len(raw) > MAX_PLAN_TASKS:
            return f"한 계획에는 작업을 {MAX_PLAN_TASKS}개까지 넣을 수 있습니다. 나누어 요청하세요."
        items: dict[str, PlanItem] = {}
        with self.factory() as db:
            me = db.get(Agent, run.agent_id)
            conv = db.get(Conversation, conversation_id)
            if me is None or conv is None:
                return "계획을 실행할 수 없습니다: 실행 정보를 찾지 못했습니다."
            for entry in raw:
                if not isinstance(entry, dict):
                    return "각 작업은 {key, assignee, title, brief, depends_on, review_by} 객체여야 합니다."
                key = str(entry.get("key") or "").strip()
                if not key or key in items:
                    return f"작업 key가 비었거나 중복입니다: '{key}'"
                target, problem = self._check_target(db, run, me, str(entry.get("assignee") or ""))
                if target is None:
                    return f"[{key}] {problem}"
                reviewer_id = None
                if entry.get("review_by"):
                    reviewer, problem = self._check_target(db, run, me, str(entry["review_by"]))
                    if reviewer is None:
                        return f"[{key}] 검토자: {problem}"
                    if reviewer.id == target.id:
                        return f"[{key}] 담당자와 검토자는 달라야 합니다."
                    reviewer_id = reviewer.id
                brief = str(entry.get("brief") or "").strip()
                if not brief:
                    return f"[{key}] brief(업무 지시)가 비어 있습니다."
                deps = [str(d) for d in entry.get("depends_on") or []]
                items[key] = PlanItem(
                    key,
                    target.id,
                    target.name,
                    str(entry.get("title") or key)[:200],
                    brief,
                    deps,
                    reviewer_id,
                )
            for item in items.values():
                missing = [d for d in item.depends_on if d not in items]
                if missing:
                    return f"[{item.key}] 없는 선행 작업: {', '.join(missing)}"
            cycle = _find_cycle(items)
            if cycle:
                return "선행 작업에 순환이 있습니다: " + " → ".join(cycle)
            for item in items.values():
                target = db.get(Agent, item.assignee_id)
                assert target is not None
                task = self._new_task(
                    db, me, conv, target, item.title, item.brief, run.task_id, status="queued"
                )
                item.task_id = task.id
            for item in items.values():
                row = db.get(Task, item.task_id)
                if row is not None:
                    row.depends_on = [items[d].task_id for d in item.depends_on]
            db.add(
                ActivityEvent(
                    organization_id=me.organization_id,
                    agent_id=me.id,
                    kind="task.planned",
                    summary=f"{me.name}: 작업 계획 {len(items)}건 시작",
                )
            )
            db.commit()
            me_snapshot = (me.name, me.title, me.organization_id)
        self.bus.publish("task.updated", organization_id=me_snapshot[2], task_id="", status="planned")
        locks: dict[str, asyncio.Lock] = {}
        results: dict[str, tuple[str, str]] = {}
        async with self._slot_released():
            pending = set(items)
            running: dict[asyncio.Task[tuple[str, str]], str] = {}
            while pending or running:
                for key in sorted(pending):
                    deps = items[key].depends_on
                    if any(d in results and results[d][0] != "done" for d in deps):
                        pending.discard(key)
                        results[key] = ("cancelled", "선행 작업이 완료되지 않아 실행하지 않았습니다.")
                        self._set_task(items[key].task_id, "cancelled", results[key][1])
                    elif all(d in results for d in deps):
                        pending.discard(key)
                        job = asyncio.create_task(
                            self._plan_item(
                                run, conversation_id, me_snapshot, items[key], items, results, locks
                            )
                        )
                        running[job] = key
                if not running:
                    break
                finished, _ = await asyncio.wait(running, return_when=asyncio.FIRST_COMPLETED)
                for job in finished:
                    key = running.pop(job)
                    try:
                        results[key] = job.result()
                    except Exception as exc:  # 한 작업의 예외가 계획 전체를 멈추지 않게
                        results[key] = ("failed", f"{type(exc).__name__}: {exc}"[:300])
                        self._set_task(items[key].task_id, "failed", results[key][1])
        lines = [f"[작업 계획 결과 — {len(items)}건]"]
        for key, item in items.items():
            status, body = results.get(key, ("unknown", ""))
            lines.append(f"\n## {item.title} ({item.assignee_name}) — {PLAN_STATUS.get(status, status)}")
            lines.append(body[:PLAN_REPORT])
        return "\n".join(lines)

    async def _plan_item(
        self,
        run: ActiveRun,
        conversation_id: str,
        me: tuple[str, str, str],
        item: PlanItem,
        items: dict[str, PlanItem],
        results: dict[str, tuple[str, str]],
        locks: dict[str, asyncio.Lock],
    ) -> tuple[str, str]:
        me_name, me_title, _org = me
        brief = item.brief
        if item.depends_on:
            brief += "\n\n[선행 작업 결과]"
            for dep in item.depends_on:
                brief += (
                    f"\n### {items[dep].title} ({items[dep].assignee_name})\n{results[dep][1][:DEP_EXCERPT]}"
                )
        feedback: str | None = None
        reviewer_name = ""
        for attempt in range(MAX_REVISIONS + 1):
            verb = "위임" if attempt == 0 else f"재작업 요청({attempt}회차)"
            work = (
                brief if feedback is None else f"{brief}\n\n[검토 의견 — 반영해 다시 작업하세요]\n{feedback}"
            )
            header = (
                f"[{me_name}({me_title})의 {verb}] 아래 업무를 처리하고, "
                f"결과를 {me_name}에게 보고하는 형식으로 정리하세요.\n작업: {item.title}\n\n"
            )
            async with locks.setdefault(item.assignee_id, asyncio.Lock()):
                await self._wait_agent_free(conversation_id, item.assignee_id)
                self._set_task(item.task_id, "running")
                mid = self._start_child(
                    run, conversation_id, item.assignee_id, header, work, item.task_id, "delegated"
                )
                status, body = await self._wait_child(mid, item.task_id)
            if status != "done":
                return status, body
            if item.reviewer_id is None:
                return "done", body
            with self.factory() as db:
                reviewer = db.get(Agent, item.reviewer_id)
                me_row = db.get(Agent, run.agent_id)
                conv = db.get(Conversation, conversation_id)
                assert reviewer is not None and me_row is not None and conv is not None
                reviewer_name = reviewer.name
                review_task = self._new_task(
                    db, me_row, conv, reviewer, f"검토: {item.title}", body[:2000], item.task_id
                )
                db.commit()
                review_task_id = review_task.id
            review_brief = (
                "아래 결과물을 검토하세요. 답의 첫 줄은 반드시 `[승인]` 또는 `[수정 요청]`으로 시작하고, "
                "수정 요청이면 고칠 점을 구체적으로 적으세요.\n\n"
                f"[작업 지시(선행 작업 결과 포함)]\n{brief}\n\n[결과물]\n{body[:MAX_REPORT]}"
            )
            review_header = f"[{me_name}({me_title})의 검토 요청] 작업: {item.title}\n\n"
            async with locks.setdefault(item.reviewer_id, asyncio.Lock()):
                await self._wait_agent_free(conversation_id, item.reviewer_id)
                mid = self._start_child(
                    run,
                    conversation_id,
                    item.reviewer_id,
                    review_header,
                    review_brief,
                    review_task_id,
                    "review",
                )
                review_status, review = await self._wait_child(mid, review_task_id)
            if review_status == "done" and APPROVED.match(review):
                self._set_task(item.task_id, "done")
                return "done", f"{body}\n\n(검토 승인: {reviewer_name})"
            feedback = review
        self._set_task(item.task_id, "review", f"{MAX_REVISIONS}회 재작업 후에도 검토 미승인")
        return "review", f"{body}\n\n(검토 미승인 — {reviewer_name}: {(feedback or '')[:600]})"

    def _set_task(self, task_id: str, status: str, result: str | None = None) -> None:
        with self.factory() as db:
            task = db.get(Task, task_id)
            if task is None:
                return
            task.status = status
            if result is not None:
                task.result = result[:MAX_TASK_RESULT]
            db.commit()
            org_id = task.organization_id
        self.bus.publish("task.updated", organization_id=org_id, task_id=task_id, status=status)

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
