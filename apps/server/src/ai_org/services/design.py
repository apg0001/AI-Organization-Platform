"""조직 설계 서비스: 템플릿 로딩, 조직 ↔ 명세 변환, 적용(+변경 이력), AI 제안 정리, 추천 상태.

설계 모드와 운영 모드 분리:
- 설계 대화의 Claude는 '조직 설계 담당자'다. 도구 없이(tools=[]) 구조화 출력(JSON 스키마)만 돌려준다.
  조직 구성원 에이전트·세션과 섞이지 않는다(별도 OrgDesign 메시지·세션 ID).
- 설계는 OrgDesign.spec(단일 상태)만 바꾼다. 사용자가 '적용'을 눌러야 실제 조직이 바뀐다.
"""

from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_org.models import ActivityEvent, Agent, Collaboration, Department, Organization, OrgRevision
from ai_org.schemas import AgentPermissions
from ai_org.services.capabilities import Capability
from ai_org.spec import OrgSpec, SpecAgent, SpecCollaboration, SpecDepartment, TemplateFile

DEPT_COLORS = [f"dept-{i}" for i in range(1, 9)]


# ── 템플릿 ─────────────────────────────────────────────────────────────────


@lru_cache(maxsize=1)
def load_templates() -> tuple[TemplateFile, ...]:
    folder = resources.files("ai_org") / "templates"
    found = []
    for entry in sorted(folder.iterdir(), key=lambda p: p.name):
        if entry.name.endswith(".json"):
            found.append(TemplateFile.model_validate(json.loads(entry.read_text(encoding="utf-8"))))
    return tuple(found)


def get_template(template_id: str) -> TemplateFile | None:
    return next((t for t in load_templates() if t.template_id == template_id), None)


def blank_spec(name: str = "새 조직") -> OrgSpec:
    return OrgSpec(
        name=name,
        agents=[
            SpecAgent(
                key="ceo",
                name="CEO",
                title="대표",
                role="사용자의 업무 지시를 받아 분석하고 적합한 에이전트에게 분배한 뒤 결과를 보고한다.",
                is_lead=True,
                permissions=AgentPermissions(can_delegate=True),
            )
        ],
    )


# ── 조직 ↔ 명세 ────────────────────────────────────────────────────────────


def org_to_spec(db: Session, org: Organization) -> OrgSpec:
    depts = list(
        db.scalars(
            select(Department).where(Department.organization_id == org.id).order_by(Department.sort_order)
        )
    )
    agents = list(db.scalars(select(Agent).where(Agent.organization_id == org.id).order_by(Agent.created_at)))
    collabs = list(db.scalars(select(Collaboration).where(Collaboration.organization_id == org.id)))
    policy = org.policy or {}
    return OrgSpec(
        name=org.name,
        description=org.description,
        mission=org.mission,
        base_instructions=org.base_instructions,
        policy=policy,  # type: ignore[arg-type]
        departments=[
            SpecDepartment(key=d.id, name=d.name, description=d.description, color=d.color) for d in depts
        ],
        agents=[
            SpecAgent(
                key=a.id,
                name=a.name,
                title=a.title,
                department=a.department_id,
                role=a.role,
                responsibilities=a.responsibilities or [],
                expertise=a.expertise or [],
                instructions=a.instructions,
                reports_to=a.reports_to_id,
                is_lead=a.is_lead,
                enabled=a.enabled,
                permissions=AgentPermissions.model_validate(a.permissions or {}),
                allowed_skills=a.allowed_skills or [],
                allowed_mcp_servers=a.allowed_mcp_servers or [],
                allowed_plugins=a.allowed_plugins or [],
                model=a.model,
            )
            for a in agents
        ],
        collaborations=[
            SpecCollaboration(source=c.source_agent_id, target=c.target_agent_id, kind=c.kind, label=c.label)  # type: ignore[arg-type]
            for c in collabs
        ],
    )


def summarize_diff(before: OrgSpec | None, after: OrgSpec) -> list[str]:
    if before is None:
        return [f"조직 '{after.name}' 생성: 부서 {len(after.departments)}개, 에이전트 {len(after.agents)}명"]
    out: list[str] = []
    b_agents = {a.key: a for a in before.agents}
    a_agents = {a.key: a for a in after.agents}
    for key, agent in a_agents.items():
        if key not in b_agents:
            out.append(f"에이전트 추가: {agent.name}")
        elif agent.model_dump(exclude={"permission_suggestion"}) != b_agents[key].model_dump(
            exclude={"permission_suggestion"}
        ):
            old = b_agents[key]
            if agent.permissions != old.permissions:
                out.append(f"권한 변경: {agent.name}")
            elif agent.reports_to != old.reports_to or agent.department != old.department:
                out.append(f"소속·보고 관계 변경: {agent.name}")
            else:
                out.append(f"에이전트 수정: {agent.name}")
    out += [f"에이전트 삭제: {a.name}" for k, a in b_agents.items() if k not in a_agents]
    b_depts = {d.key: d for d in before.departments}
    a_depts = {d.key: d for d in after.departments}
    out += [f"부서 추가: {d.name}" for k, d in a_depts.items() if k not in b_depts]
    out += [f"부서 삭제: {d.name}" for k, d in b_depts.items() if k not in a_depts]
    out += [f"부서 수정: {d.name}" for k, d in a_depts.items() if k in b_depts and d != b_depts[k]]
    b_col = {(c.source, c.target, c.kind) for c in before.collaborations}
    a_col = {(c.source, c.target, c.kind) for c in after.collaborations}
    if b_col != a_col:
        out.append(f"협업 관계 변경: +{len(a_col - b_col)} / -{len(b_col - a_col)}")
    meta = ("name", "description", "mission", "base_instructions", "policy", "workflows")
    if any(getattr(before, f) != getattr(after, f) for f in meta):
        out.append("조직 정보·정책 변경")
    return out or ["변경 없음"]


def apply_spec(
    db: Session, spec: OrgSpec, org: Organization | None, source: str
) -> tuple[Organization, list[str]]:
    """명세를 실제 조직에 반영한다. key가 기존 ID와 같으면 갱신, 아니면 생성, 명세에 없으면 삭제."""
    before = org_to_spec(db, org) if org is not None else None
    if org is None:
        org = Organization(name=spec.name)
        db.add(org)
        db.flush()
    org.name, org.description, org.mission = spec.name, spec.description, spec.mission
    org.base_instructions, org.policy = spec.base_instructions, spec.policy.model_dump()

    existing_depts = {
        d.id: d for d in db.scalars(select(Department).where(Department.organization_id == org.id))
    }
    dept_ids: dict[str, str] = {}
    for index, sd in enumerate(spec.departments):
        dept = existing_depts.pop(sd.key, None)
        if dept is None:
            dept = Department(organization_id=org.id)
            db.add(dept)
        dept.name, dept.description, dept.color, dept.sort_order = sd.name, sd.description, sd.color, index
        db.flush()
        dept_ids[sd.key] = dept.id

    existing_agents = {a.id: a for a in db.scalars(select(Agent).where(Agent.organization_id == org.id))}
    agent_ids: dict[str, str] = {}
    rows: dict[str, Agent] = {}
    for sa in spec.agents:
        agent = existing_agents.pop(sa.key, None)
        if agent is None:
            agent = Agent(organization_id=org.id)
            db.add(agent)
        agent.name, agent.title, agent.role = sa.name, sa.title, sa.role
        agent.responsibilities, agent.expertise = list(sa.responsibilities), list(sa.expertise)
        agent.instructions, agent.is_lead, agent.enabled, agent.model = (
            sa.instructions,
            sa.is_lead,
            sa.enabled,
            sa.model,
        )
        agent.department_id = dept_ids.get(sa.department) if sa.department else None
        agent.permissions = sa.permissions.model_dump()
        agent.allowed_skills, agent.allowed_mcp_servers = (
            list(sa.allowed_skills),
            list(sa.allowed_mcp_servers),
        )
        agent.allowed_plugins = list(sa.allowed_plugins)
        db.flush()
        agent_ids[sa.key], rows[sa.key] = agent.id, agent
    for sa in spec.agents:
        rows[sa.key].reports_to_id = agent_ids[sa.reports_to] if sa.reports_to else None
    for removed in existing_agents.values():
        db.delete(removed)
    for removed_dept in existing_depts.values():
        db.delete(removed_dept)
    for collab in db.scalars(select(Collaboration).where(Collaboration.organization_id == org.id)):
        db.delete(collab)
    db.flush()
    for c in spec.collaborations:
        db.add(
            Collaboration(
                organization_id=org.id,
                source_agent_id=agent_ids[c.source],
                target_agent_id=agent_ids[c.target],
                kind=c.kind,
                label=c.label,
            )
        )
    db.flush()
    after = org_to_spec(db, org)
    changes = summarize_diff(before, after)
    db.add(
        OrgRevision(
            organization_id=org.id,
            spec=after.model_dump(mode="json"),
            summary=changes,
            source=source,
        )
    )
    db.add(
        ActivityEvent(
            organization_id=org.id, kind="org.applied", summary=f"조직 '{org.name}' 구성 적용: {changes[0]}"
        )
    )
    return org, changes


# ── AI 제안 정리 ───────────────────────────────────────────────────────────


def _broader(proposed: AgentPermissions, current: AgentPermissions) -> bool:
    """proposed가 current보다 넓은 권한을 주는가."""
    flags = ("allow_shell", "allow_network", "allow_file_write", "allow_file_delete", "can_delegate")
    if any(getattr(proposed, f) and not getattr(current, f) for f in flags):
        return True
    if set(current.require_approval) - set(proposed.require_approval):
        return True
    if proposed.permission_mode != current.permission_mode and proposed.permission_mode == "acceptEdits":
        return True
    return bool(current.file_scope) and not set(proposed.file_scope) <= set(current.file_scope)


def sanitize_proposal(proposal: OrgSpec, current: OrgSpec) -> tuple[OrgSpec, list[str]]:
    """AI 제안을 안전하게 만든다.

    - 권한을 넓히는 제안은 permissions에 넣지 않고 permission_suggestion으로 옮긴다(사용자 확인 필요).
    - allowed_skills/allowed_mcp_servers/allowed_plugins(실제 허용)는 AI가 바꿀 수 없다. 현재 값을 유지한다.
    """
    notes: list[str] = []
    by_key = {a.key: a for a in current.agents}
    agents = []
    for agent in proposal.agents:
        base = by_key.get(agent.key)
        base_perms = base.permissions if base else AgentPermissions(can_delegate=agent.is_lead)
        updates: dict[str, Any] = {
            "allowed_skills": base.allowed_skills if base else [],
            "allowed_mcp_servers": base.allowed_mcp_servers if base else [],
            "allowed_plugins": base.allowed_plugins if base else [],
            "permission_suggestion": None,
        }
        if _broader(agent.permissions, base_perms):
            updates["permissions"] = base_perms
            updates["permission_suggestion"] = agent.permissions
            notes.append(f"'{agent.name}'의 권한 확대 제안은 검토 대기 중입니다.")
        agents.append(agent.model_copy(update=updates))
    return proposal.model_copy(update={"agents": agents}), notes


# ── 추천 상태 ──────────────────────────────────────────────────────────────


def recommendation_status(spec: OrgSpec, caps: list[Capability]) -> list[dict[str, Any]]:
    """추천된 Skills/MCP를 실제 탐색 결과와 비교한다. 없는 도구를 있는 것처럼 표시하지 않는다.

    status: available(사용 가능, 에이전트 허용됨) | approval_required(설치됨, 허용 전)
          | install_required(이 컴퓨터에 없음) | unsupported(런타임이 지원하지 않음 — 현재 해당 없음)
    """
    skills = {c.name.lower(): c for c in caps if c.kind == "skill"}
    mcps = {c.name.lower(): c for c in caps if c.kind == "mcp"}
    out: list[dict[str, Any]] = []
    for agent in spec.agents:
        for name in agent.recommended_skills:
            cap = skills.get(name.lower())
            if cap is None:
                status = "install_required"
            elif cap.id in agent.allowed_skills:
                status = "available"
            else:
                status = "approval_required"
            out.append(
                {
                    "agent": agent.key,
                    "kind": "skill",
                    "name": name,
                    "status": status,
                    "id": cap.id if cap else None,
                }
            )
        for name in agent.recommended_mcp:
            cap = mcps.get(name.lower())
            if cap is None:
                status = "install_required"
            elif cap.id in agent.allowed_mcp_servers:
                status = "available"
            else:
                status = "approval_required"
            out.append(
                {
                    "agent": agent.key,
                    "kind": "mcp",
                    "name": name,
                    "status": status,
                    "id": cap.id if cap else None,
                }
            )
    return out


def designer_prompt(
    spec: OrgSpec, message: str, templates: tuple[TemplateFile, ...], caps: list[Capability]
) -> str:
    catalog = ", ".join(f"{t.template_id}({t.name})" for t in templates)
    skill_names = ", ".join(sorted({c.name for c in caps if c.kind == "skill"})) or "(없음)"
    mcp_names = ", ".join(sorted({c.name for c in caps if c.kind == "mcp"})) or "(없음)"
    return "\n".join(
        [
            "<current_spec>",
            spec.model_dump_json(exclude={"agents": {"__all__": {"permission_suggestion"}}}),
            "</current_spec>",
            f"<available_skills>{skill_names}</available_skills>",
            f"<configured_mcp>{mcp_names}</configured_mcp>",
            f"<templates>{catalog}</templates>",
            "",
            message,
        ]
    )


DESIGNER_SYSTEM = """# 역할: AI 조직 설계 담당자
당신은 사용자가 자신만의 AI 조직(가상 회사)을 설계하도록 돕는 설계 담당자입니다. 조직 구성원이 아닙니다.
사용자의 목적에 맞는 부서·에이전트·보고 관계·협업 관계·업무 흐름을 설계합니다.

규칙:
- <current_spec>이 현재 설계 상태입니다(사용자가 조직도에서 직접 고친 내용 포함).
  항상 이것을 기준으로 수정하세요.
- 바꿀 필요가 있을 때만 spec에 전체 수정본을 넣고, 질문만 할 때는 spec을 null로 두세요.
- 정보가 부족하면 가장 중요한 질문 1~2개만 하세요. 이미 확인된 내용은 다시 묻지 마세요.
- 세부 사항이 없으면 합리적인 기본안을 제시하되, 셸 실행·파일 삭제·자동 편집 같은 위험 권한은 켜지 마세요
  (기본 permissions를 유지하세요. 필요해 보이면 reply에서 사용자가 직접 켜도록 안내하세요).
- 기존 에이전트·부서의 key는 바꾸지 마세요. 새 항목은 짧은 영문 key를 만드세요.
- CEO(is_lead=true)는 정확히 한 명입니다.
- 추천 Skills/MCP는 recommended_skills/recommended_mcp에 이름만 적으세요. <available_skills>에 없는 것은
  '설치 필요'로 표시됩니다. 존재하지 않는 도구를 지어내지 마세요.
- 각 에이전트 instructions에는 그 역할의 작업 방식과 결과물 형식을 2~5문장으로 적으세요.
- reply는 사용자의 언어로, 무엇을 왜 바꿨는지 짧게 설명하세요."""


def designer_schema() -> dict[str, Any]:
    spec_schema = OrgSpec.model_json_schema()
    return {
        "type": "object",
        "properties": {
            "reply": {"type": "string"},
            "questions": {"type": "array", "items": {"type": "string"}},
            "spec": {"anyOf": [spec_schema, {"type": "null"}]},
        },
        "required": ["reply", "spec"],
        "$defs": spec_schema.pop("$defs", {}),
    }
