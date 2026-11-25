"""API 입출력 스키마. ORM 모델과 분리해 계약을 명시한다."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

AgentStatus = Literal["idle", "thinking", "working", "waiting", "reviewing", "completed", "failed", "offline"]
CollaborationKind = Literal["handoff", "review", "consult"]
PermissionMode = Literal["default", "acceptEdits", "plan"]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ── 정책 ───────────────────────────────────────────────────────────────────


class AgentPermissions(BaseModel):
    """에이전트 권한. Claude Code 권한 위에 덧씌우는 '더 좁히기 전용' 정책이다.

    - permission_mode: Claude Code permission mode. bypassPermissions는 의도적으로 허용하지 않는다.
    - file_scope: 작업 가능한 디렉터리(프로젝트 루트 기준 상대 경로 또는 절대 경로). 비면 프로젝트 전체.
    - allow_shell / allow_network / allow_file_write / allow_file_delete: 도구 묶음 허용 여부.
    - require_approval: 사용자 승인을 받아야 하는 도구 묶음.
    - can_delegate: 다른 에이전트에게 업무를 위임할 수 있는지.
    """

    permission_mode: PermissionMode = "default"
    file_scope: list[str] = Field(default_factory=list)
    allow_shell: bool = False
    allow_network: bool = True
    allow_file_write: bool = True
    allow_file_delete: bool = False
    require_approval: list[Literal["shell", "file_write", "file_delete", "network", "delegate"]] = Field(
        default_factory=lambda: ["shell", "file_write", "file_delete"]  # type: ignore[arg-type]
    )
    can_delegate: bool = False


class OrgPolicy(BaseModel):
    max_concurrent_agents: int = Field(default=3, ge=1, le=16)
    require_plan_approval: bool = True
    default_permission_mode: PermissionMode = "default"


# ── 조직 ───────────────────────────────────────────────────────────────────


class DepartmentIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    description: str = ""
    color: str = "dept-1"
    sort_order: int = 0


class DepartmentOut(ORM):
    id: str
    organization_id: str
    name: str
    description: str
    color: str
    sort_order: int


class AgentBase(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    title: str = ""
    role: str = ""
    responsibilities: list[str] = Field(default_factory=list)
    expertise: list[str] = Field(default_factory=list)
    instructions: str = ""
    department_id: str | None = None
    reports_to_id: str | None = None
    is_lead: bool = False
    enabled: bool = True
    runtime: Literal["claude-code"] = "claude-code"
    model: str | None = None
    allowed_skills: list[str] = Field(default_factory=list)
    allowed_mcp_servers: list[str] = Field(default_factory=list)
    allowed_plugins: list[str] = Field(default_factory=list)
    permissions: AgentPermissions = Field(default_factory=AgentPermissions)
    pos_x: float | None = None
    pos_y: float | None = None


class AgentIn(AgentBase):
    pass


class AgentPatch(BaseModel):
    """부분 수정. 보낸 필드만 바꾼다."""

    name: str | None = Field(default=None, min_length=1, max_length=80)
    title: str | None = None
    role: str | None = None
    responsibilities: list[str] | None = None
    expertise: list[str] | None = None
    instructions: str | None = None
    department_id: str | None = None
    reports_to_id: str | None = None
    is_lead: bool | None = None
    enabled: bool | None = None
    model: str | None = None
    allowed_skills: list[str] | None = None
    allowed_mcp_servers: list[str] | None = None
    allowed_plugins: list[str] | None = None
    permissions: AgentPermissions | None = None
    pos_x: float | None = None
    pos_y: float | None = None


class AgentOut(ORM, AgentBase):
    id: str
    organization_id: str
    status: AgentStatus
    created_at: datetime
    updated_at: datetime


class CollaborationIn(BaseModel):
    source_agent_id: str
    target_agent_id: str
    kind: CollaborationKind = "handoff"
    label: str = ""


class CollaborationOut(ORM):
    id: str
    organization_id: str
    source_agent_id: str
    target_agent_id: str
    kind: CollaborationKind
    label: str


class OrganizationIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = ""
    mission: str = ""
    base_instructions: str = ""
    policy: OrgPolicy = Field(default_factory=OrgPolicy)
    template_key: str | None = None


class OrganizationPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = None
    mission: str | None = None
    base_instructions: str | None = None
    policy: OrgPolicy | None = None
    default_project_id: str | None = None


class OrganizationSummary(ORM):
    id: str
    name: str
    description: str
    mission: str
    template_key: str | None
    agent_count: int = 0
    department_count: int = 0
    project_count: int = 0
    created_at: datetime
    updated_at: datetime


class OrganizationOut(ORM):
    id: str
    name: str
    description: str
    mission: str
    base_instructions: str
    policy: OrgPolicy
    template_key: str | None
    default_project_id: str | None
    created_at: datetime
    updated_at: datetime
    departments: list[DepartmentOut]
    agents: list[AgentOut]
    collaborations: list[CollaborationOut]


class LayoutItem(BaseModel):
    id: str
    x: float
    y: float


class LayoutIn(BaseModel):
    positions: list[LayoutItem]


# ── 템플릿 ─────────────────────────────────────────────────────────────────


class TemplateSummary(BaseModel):
    key: str
    name: str
    description: str
    departments: list[str]
    agent_count: int


class FromTemplateIn(BaseModel):
    template_key: str
    name: str | None = Field(default=None, max_length=120)


# ── 프로젝트 ───────────────────────────────────────────────────────────────


class ProjectRootIn(BaseModel):
    path: str = Field(min_length=1)
    max_depth: int = Field(default=2, ge=0, le=4)


class ProjectRootOut(ORM):
    id: str
    path: str
    max_depth: int
    exists: bool = True


class ProjectCandidate(BaseModel):
    name: str
    path: str
    kind: str
    is_git: bool
    registered: bool


class ProjectIn(BaseModel):
    path: str = Field(min_length=1)
    name: str | None = Field(default=None, max_length=120)
    description: str = ""
    organization_id: str | None = None


class ProjectPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = None
    organization_id: str | None = None


class GitInfo(BaseModel):
    is_repo: bool
    branch: str | None = None
    head: str | None = None
    head_subject: str | None = None
    dirty_files: int = 0
    ahead: int | None = None
    behind: int | None = None
    remote: str | None = None
    error: str | None = None


class ProjectOut(ORM):
    id: str
    name: str
    path: str
    description: str
    kind: str
    organization_id: str | None
    exists: bool = True
    created_at: datetime
    updated_at: datetime


class ProjectDetail(ProjectOut):
    git: GitInfo


# ── 실행 기록(Phase 3·5에서 채워짐) ────────────────────────────────────────


class TaskOut(ORM):
    id: str
    organization_id: str
    project_id: str | None
    parent_id: str | None
    assignee_id: str | None
    title: str
    status: str
    priority: int
    created_at: datetime
    updated_at: datetime


class ApprovalOut(ORM):
    id: str
    organization_id: str
    agent_id: str
    kind: str
    summary: str
    detail: dict[str, Any] = Field(default_factory=dict)
    status: str
    created_at: datetime


class ActivityOut(ORM):
    id: str
    organization_id: str | None
    agent_id: str | None
    kind: str
    summary: str
    created_at: datetime


class WorkspaceOverview(BaseModel):
    organizations: list[OrganizationSummary]
    projects: list[ProjectOut]
    running_agents: list[AgentOut]
    recent_tasks: list[TaskOut]
    pending_approvals: list[ApprovalOut]
    activity: list[ActivityOut]


# ── 시스템 ─────────────────────────────────────────────────────────────────


class RuntimeInfo(BaseModel):
    id: str
    name: str
    available: bool
    version: str | None = None
    path: str | None = None
    detail: str | None = None


class SystemInfo(BaseModel):
    version: str
    data_dir: str
    runtimes: list[RuntimeInfo]
