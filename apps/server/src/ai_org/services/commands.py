"""슬래시 명령 레지스트리.

명령은 이름·설명·사용법·인자 명세·핸들러로 등록한다. 핸들러는 실제 플랫폼 기능(조회·위임·중지·대화
설정)을 호출하고 구조화된 결과를 돌려준다. 화면은 결과의 kind(list/text/action)에 따라 그린다.
새 명령은 @command 데코레이터로 추가한다.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_org.models import Agent, Approval, Conversation, Department, Project, Task
from ai_org.services.capabilities import discover_all
from ai_org.services.runs import Route, RouteError, RunManager

ArgKind = Literal["agent", "department", "project", "text"]


@dataclass(frozen=True)
class Arg:
    name: str
    kind: ArgKind
    required: bool = True
    description: str = ""


@dataclass
class CommandContext:
    db: Session
    conversation: Conversation
    args: dict[str, str]
    runs: RunManager
    claude_home: Any


@dataclass
class CommandResult:
    kind: Literal["list", "text", "action"]
    title: str
    text: str = ""
    columns: list[str] = field(default_factory=list)
    rows: list[list[str]] = field(default_factory=list)
    action: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "title": self.title,
            "text": self.text,
            "columns": self.columns,
            "rows": self.rows,
            "action": self.action,
        }


Handler = Callable[[CommandContext], Awaitable[CommandResult]]


@dataclass(frozen=True)
class Command:
    name: str
    description: str
    usage: str
    args: tuple[Arg, ...]
    handler: Handler

    def spec(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "usage": self.usage,
            "args": [a.__dict__ for a in self.args],
        }


REGISTRY: dict[str, Command] = {}


class CommandError(ValueError):
    pass


def command(name: str, description: str, usage: str, *args: Arg) -> Callable[[Handler], Handler]:
    def register(fn: Handler) -> Handler:
        REGISTRY[name] = Command(name, description, usage, tuple(args), fn)
        return fn

    return register


def _agent(ctx: CommandContext, ref: str) -> Agent:
    agent = ctx.db.get(Agent, ref)
    if agent is None:
        agent = ctx.db.scalar(
            select(Agent).where(
                Agent.organization_id == ctx.conversation.organization_id, Agent.name == ref.lstrip("@")
            )
        )
    if agent is None or agent.organization_id != ctx.conversation.organization_id:
        raise CommandError(f"에이전트를 찾을 수 없습니다: {ref}")
    return agent


def _org_agents(ctx: CommandContext) -> list[Agent]:
    return list(
        ctx.db.scalars(
            select(Agent)
            .where(Agent.organization_id == ctx.conversation.organization_id)
            .order_by(Agent.created_at)
        )
    )


STATUS_LABELS = {
    "idle": "대기",
    "thinking": "생각 중",
    "working": "작업 중",
    "waiting": "승인 대기",
    "reviewing": "검토 중",
    "completed": "완료",
    "failed": "실패",
    "offline": "오프라인",
}


@command("help", "사용할 수 있는 명령을 보여 줍니다.", "/help")
async def _help(ctx: CommandContext) -> CommandResult:
    return CommandResult(
        "list",
        "명령어",
        columns=["명령", "설명"],
        rows=[[c.usage, c.description] for c in REGISTRY.values()],
    )


@command("agents", "조직 구성원과 현재 상태를 보여 줍니다.", "/agents")
async def _agents(ctx: CommandContext) -> CommandResult:
    depts = {
        d.id: d.name
        for d in ctx.db.scalars(
            select(Department).where(Department.organization_id == ctx.conversation.organization_id)
        )
    }
    return CommandResult(
        "list",
        "에이전트",
        columns=["이름", "직책", "부서", "상태"],
        rows=[
            [
                a.name + ("" if a.enabled else " (비활성)"),
                a.title,
                depts.get(a.department_id or "", "—"),
                STATUS_LABELS.get(a.status, a.status),
            ]
            for a in _org_agents(ctx)
        ],
    )


@command(
    "delegate",
    "에이전트에게 업무를 위임합니다. 작업으로 기록되고 그 에이전트가 바로 실행합니다.",
    "/delegate @에이전트 업무 내용",
    Arg("agent", "agent", description="담당 에이전트"),
    Arg("task", "text", description="업무 내용"),
)
async def _delegate(ctx: CommandContext) -> CommandResult:
    agent = _agent(ctx, ctx.args.get("agent", ""))
    brief = ctx.args.get("task", "").strip()
    if not brief:
        raise CommandError("업무 내용을 입력하세요.")
    if not agent.enabled:
        raise CommandError(f"'{agent.name}'은(는) 비활성화되어 있습니다.")
    task = Task(
        organization_id=ctx.conversation.organization_id,
        project_id=ctx.conversation.project_id,
        assignee_id=agent.id,
        title=brief.splitlines()[0][:200],
        brief=brief,
        status="running",
    )
    ctx.db.add(task)
    ctx.db.commit()
    try:
        ctx.runs.launch(ctx.db, ctx.conversation, Route(agent, "agent"), brief, [], task_id=task.id)
    except RouteError as exc:
        task.status = "failed"
        ctx.db.commit()
        raise CommandError(str(exc)) from exc
    return CommandResult(
        "text", "업무 위임", text=f"'{agent.name}'에게 작업 「{task.title}」을(를) 위임했습니다."
    )


@command(
    "team",
    "대화 대상을 부서(팀)로 바꿉니다.",
    "/team 부서",
    Arg("department", "department", description="부서"),
)
async def _team(ctx: CommandContext) -> CommandResult:
    ref = ctx.args.get("department", "")
    dept = ctx.db.get(Department, ref) or ctx.db.scalar(
        select(Department).where(
            Department.organization_id == ctx.conversation.organization_id, Department.name == ref
        )
    )
    if dept is None or dept.organization_id != ctx.conversation.organization_id:
        raise CommandError(f"부서를 찾을 수 없습니다: {ref}")
    ctx.conversation.target_kind, ctx.conversation.target_id = "team", dept.id
    ctx.db.commit()
    return CommandResult(
        "action",
        "대화 대상 변경",
        text=f"이제 '{dept.name}' 팀과 대화합니다.",
        action={"type": "conversation.updated"},
    )


@command(
    "project",
    "대화에 로컬 프로젝트를 연결합니다. 에이전트는 이 프로젝트 폴더에서 작업합니다.",
    "/project 프로젝트",
    Arg("project", "project", description="등록된 프로젝트"),
)
async def _project(ctx: CommandContext) -> CommandResult:
    ref = ctx.args.get("project", "")
    project = ctx.db.get(Project, ref) or ctx.db.scalar(select(Project).where(Project.name == ref))
    if project is None:
        raise CommandError(f"등록된 프로젝트가 아닙니다: {ref}")
    ctx.conversation.project_id = project.id
    ctx.db.commit()
    return CommandResult(
        "action",
        "프로젝트 연결",
        text=f"'{project.name}'({project.path})을(를) 연결했습니다.",
        action={"type": "conversation.updated"},
    )


@command("tasks", "조직의 작업 목록을 보여 줍니다.", "/tasks")
async def _tasks(ctx: CommandContext) -> CommandResult:
    tasks = ctx.db.scalars(
        select(Task)
        .where(Task.organization_id == ctx.conversation.organization_id)
        .order_by(Task.updated_at.desc())
        .limit(30)
    ).all()
    names = {a.id: a.name for a in _org_agents(ctx)}
    if not tasks:
        return CommandResult(
            "text", "작업", text="아직 작업이 없습니다. `/delegate @에이전트 업무`로 위임할 수 있습니다."
        )
    return CommandResult(
        "list",
        "작업",
        columns=["작업", "담당", "상태"],
        rows=[[t.title, names.get(t.assignee_id or "", "—"), t.status] for t in tasks],
    )


@command("status", "조직과 실행 상태를 요약합니다.", "/status")
async def _status(ctx: CommandContext) -> CommandResult:
    agents = _org_agents(ctx)
    org_id = ctx.conversation.organization_id
    running = [r for r in ctx.runs.runs.values() if any(a.id == r.agent_id for a in agents)]
    pending = ctx.db.scalars(
        select(Approval).where(Approval.organization_id == org_id, Approval.status == "pending")
    ).all()
    open_tasks = ctx.db.scalars(
        select(Task).where(Task.organization_id == org_id, Task.status.in_(("queued", "running", "waiting")))
    ).all()
    counts: dict[str, int] = {}
    for a in agents:
        counts[a.status] = counts.get(a.status, 0) + 1
    rows = [[STATUS_LABELS.get(k, k), str(v)] for k, v in sorted(counts.items())]
    rows += [
        ["실행 중인 세션", str(len(running))],
        ["승인 대기", str(len(pending))],
        ["진행 중 작업", str(len(open_tasks))],
    ]
    # 실행 중인 에이전트: 상태는 에이전트 단위(Agent.status)라 run이 여러 개여도 1행만 보인다.
    # 세션 수는 위 "실행 중인 세션" 행에 있다. 순서는 조직 구성원 순서(생성 순)를 따른다.
    running_ids = {r.agent_id for r in running}
    rows += [
        [f"실행 중: {a.name}", STATUS_LABELS.get(a.status, a.status)] for a in agents if a.id in running_ids
    ]
    return CommandResult("list", "조직 상태", columns=["항목", "값"], rows=rows)


@command("stop", "이 대화에서 실행 중인 작업을 모두 중지합니다.", "/stop")
async def _stop(ctx: CommandContext) -> CommandResult:
    count = await ctx.runs.stop(conversation_id=ctx.conversation.id)
    return CommandResult(
        "text", "중지", text=f"실행 {count}개를 중지했습니다." if count else "실행 중인 작업이 없습니다."
    )


@command("approve", "승인 대기 중인 요청을 보여 줍니다.", "/approve")
async def _approve(ctx: CommandContext) -> CommandResult:
    pending = ctx.db.scalars(
        select(Approval)
        .where(Approval.organization_id == ctx.conversation.organization_id, Approval.status == "pending")
        .order_by(Approval.created_at)
    ).all()
    if not pending:
        return CommandResult("text", "승인 대기", text="승인을 기다리는 요청이 없습니다.")
    names = {a.id: a.name for a in _org_agents(ctx)}
    return CommandResult(
        "action",
        "승인 대기",
        columns=["에이전트", "요청"],
        rows=[[names.get(p.agent_id, "—"), p.summary] for p in pending],
        action={"type": "approvals.open", "ids": [p.id for p in pending]},
    )


def _caps(ctx: CommandContext, kind: str) -> list[dict[str, Any]]:
    paths = list(ctx.db.scalars(select(Project.path)))
    return [c.to_dict() for c in discover_all(ctx.claude_home, paths) if c.kind == kind]


@command("skills", "이 컴퓨터에서 찾은 Skills와 허용된 에이전트를 보여 줍니다.", "/skills")
async def _skills(ctx: CommandContext) -> CommandResult:
    agents = _org_agents(ctx)
    caps = _caps(ctx, "skill")
    if not caps:
        return CommandResult("text", "Skills", text="등록된 Skill이 없습니다.")
    return CommandResult(
        "list",
        "Skills",
        columns=["Skill", "범위", "허용된 에이전트"],
        rows=[
            [c["name"], c["scope"], ", ".join(a.name for a in agents if c["id"] in a.allowed_skills) or "—"]
            for c in caps
        ],
    )


@command("mcp", "설정된 MCP 서버를 보여 줍니다(연결 점검은 Capability Manager에서).", "/mcp")
async def _mcp(ctx: CommandContext) -> CommandResult:
    caps = _caps(ctx, "mcp")
    if not caps:
        return CommandResult("text", "MCP", text="설정된 MCP 서버가 없습니다.")
    return CommandResult(
        "list",
        "MCP 서버",
        columns=["이름", "범위", "전송"],
        rows=[[c["name"], c["scope"], c.get("transport") or "—"] for c in caps],
    )


@command("clear", "같은 대상으로 새 대화를 시작합니다(이전 대화는 기록에 남습니다).", "/clear")
async def _clear(ctx: CommandContext) -> CommandResult:
    conv = ctx.conversation
    new = Conversation(
        organization_id=conv.organization_id,
        target_kind=conv.target_kind,
        target_id=conv.target_id,
        project_id=conv.project_id,
    )
    ctx.db.add(new)
    ctx.db.commit()
    return CommandResult(
        "action",
        "새 대화",
        text="새 대화를 시작했습니다.",
        action={"type": "conversation.open", "id": new.id},
    )


async def execute(name: str, ctx: CommandContext) -> CommandResult:
    cmd = REGISTRY.get(name)
    if cmd is None:
        raise CommandError(f"알 수 없는 명령입니다: /{name}")
    for arg in cmd.args:
        if arg.required and not ctx.args.get(arg.name, "").strip():
            raise CommandError(f"인자가 필요합니다: {arg.name} — 사용법 {cmd.usage}")
    return await cmd.handler(ctx)
