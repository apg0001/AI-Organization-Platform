"""조직 설계 명세(OrgSpec) — 템플릿·대화형 설계·조직도 편집·변경 이력이 공유하는 단일 데이터 모델.

- 템플릿 파일, 설계 초안(OrgDesign.spec), 변경 이력(OrgRevision)은 모두 이 형식을 저장한다.
- key는 명세 안에서만 쓰는 식별자다. 기존 조직에서 만든 명세는 실제 ID를 key로 쓴다.
- recommended_*는 AI·템플릿의 '추천'이고, allowed_*만 실제로 적용되는 허용 목록이다.
- permission_suggestion은 AI가 제안한 더 넓은 권한이다. 사용자가 수락하기 전에는
  permissions에 반영하지 않는다.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from ai_org.schemas import AgentPermissions, OrgPolicy

KEY = r"^[A-Za-z0-9_\-]{1,40}$"


class SpecDepartment(BaseModel):
    key: str = Field(pattern=KEY)
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=500)
    color: str = "dept-1"


class SpecAgent(BaseModel):
    key: str = Field(pattern=KEY)
    name: str = Field(min_length=1, max_length=80)
    title: str = Field(default="", max_length=80)
    department: str | None = None
    role: str = Field(default="", max_length=1000)
    responsibilities: list[str] = Field(default_factory=list, max_length=20)
    expertise: list[str] = Field(default_factory=list, max_length=20)
    instructions: str = Field(default="", max_length=8000)
    reports_to: str | None = None
    is_lead: bool = False
    enabled: bool = True
    permissions: AgentPermissions = Field(default_factory=AgentPermissions)
    permission_suggestion: AgentPermissions | None = None
    recommended_skills: list[str] = Field(default_factory=list, max_length=20)
    recommended_mcp: list[str] = Field(default_factory=list, max_length=20)
    allowed_skills: list[str] = Field(default_factory=list)
    allowed_mcp_servers: list[str] = Field(default_factory=list)
    allowed_plugins: list[str] = Field(default_factory=list)
    model: str | None = None


class SpecCollaboration(BaseModel):
    source: str
    target: str
    kind: Literal["handoff", "review", "consult"] = "handoff"
    label: str = Field(default="", max_length=120)


class SpecWorkflow(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    steps: list[str] = Field(default_factory=list, max_length=20)


class OrgSpec(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=1000)
    mission: str = Field(default="", max_length=1000)
    base_instructions: str = Field(default="", max_length=8000)
    policy: OrgPolicy = Field(default_factory=OrgPolicy)
    departments: list[SpecDepartment] = Field(default_factory=list, max_length=30)
    agents: list[SpecAgent] = Field(min_length=1, max_length=60)
    collaborations: list[SpecCollaboration] = Field(default_factory=list, max_length=200)
    workflows: list[SpecWorkflow] = Field(default_factory=list, max_length=20)
    recommended_skills: list[str] = Field(default_factory=list, max_length=30)
    recommended_mcp: list[str] = Field(default_factory=list, max_length=30)

    @model_validator(mode="after")
    def _consistent(self) -> OrgSpec:
        dept_keys = [d.key for d in self.departments]
        agent_keys = [a.key for a in self.agents]
        if len(set(dept_keys)) != len(dept_keys):
            raise ValueError("duplicate department key")
        if len(set(agent_keys)) != len(agent_keys):
            raise ValueError("duplicate agent key")
        known_depts, known_agents = set(dept_keys), set(agent_keys)
        for agent in self.agents:
            if agent.department is not None and agent.department not in known_depts:
                raise ValueError(f"agent {agent.key}: unknown department {agent.department}")
            if agent.reports_to is not None and agent.reports_to not in known_agents:
                raise ValueError(f"agent {agent.key}: unknown manager {agent.reports_to}")
            if agent.reports_to == agent.key:
                raise ValueError(f"agent {agent.key} reports to itself")
        managers = {a.key: a.reports_to for a in self.agents}
        for start in managers:
            seen: set[str] = set()
            cursor: str | None = start
            while cursor is not None:
                if cursor in seen:
                    raise ValueError("reporting lines contain a cycle")
                seen.add(cursor)
                cursor = managers.get(cursor)
        if sum(1 for a in self.agents if a.is_lead) != 1:
            raise ValueError("exactly one lead (CEO) agent is required")
        for collab in self.collaborations:
            if collab.source not in known_agents or collab.target not in known_agents:
                raise ValueError("collaboration refers to unknown agent")
            if collab.source == collab.target:
                raise ValueError("collaboration source and target must differ")
        return self


class TemplateFile(BaseModel):
    """템플릿 파일 형식(ai_org/templates/*.json). 조직 명세 + 카탈로그 메타데이터."""

    template_id: str = Field(pattern=KEY)
    version: str
    name: str
    description: str
    category: str
    target_users: list[str]
    org_size: str = ""
    spec: OrgSpec
