"""조직·부서·에이전트·협업 관계 API."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ai_org.deps import DB, not_found
from ai_org.models import ActivityEvent, Agent, Collaboration, Department, Organization, Project
from ai_org.schemas import (
    AgentIn,
    AgentOut,
    AgentPatch,
    AgentPermissions,
    CollaborationIn,
    CollaborationOut,
    DepartmentIn,
    DepartmentOut,
    FromTemplateIn,
    LayoutIn,
    OrganizationIn,
    OrganizationOut,
    OrganizationPatch,
    OrganizationSummary,
)
from ai_org.services import design

router = APIRouter(prefix="/api/v1", tags=["organizations"])


def _log(db: Session, org_id: str | None, kind: str, summary: str, agent_id: str | None = None) -> None:
    db.add(ActivityEvent(organization_id=org_id, agent_id=agent_id, kind=kind, summary=summary))


def _load_org(db: Session, org_id: str) -> Organization:
    org = db.scalar(
        select(Organization)
        .where(Organization.id == org_id)
        .options(
            selectinload(Organization.departments),
            selectinload(Organization.agents),
            selectinload(Organization.collaborations),
        )
    )
    if org is None:
        raise not_found("organization")
    return org


def _agent_in_org(db: Session, org_id: str, agent_id: str) -> Agent:
    agent = db.get(Agent, agent_id)
    if agent is None or agent.organization_id != org_id:
        raise not_found("agent")
    return agent


def _check_refs(
    db: Session, org_id: str, department_id: str | None, reports_to_id: str | None, self_id: str | None
) -> None:
    if department_id is not None:
        dept = db.get(Department, department_id)
        if dept is None or dept.organization_id != org_id:
            raise HTTPException(422, "department does not belong to this organization")
    if reports_to_id is not None:
        if reports_to_id == self_id:
            raise HTTPException(422, "an agent cannot report to itself")
        manager = _agent_in_org(db, org_id, reports_to_id)
        # 순환 방지: 새 상위 관리자의 상위 체인에 자신이 있으면 거부.
        seen: set[str] = set()
        cursor: Agent | None = manager
        while cursor is not None and cursor.id not in seen:
            if self_id is not None and cursor.id == self_id:
                raise HTTPException(422, "reporting line would create a cycle")
            seen.add(cursor.id)
            cursor = db.get(Agent, cursor.reports_to_id) if cursor.reports_to_id else None


def _single_lead(db: Session, org_id: str, lead_id: str) -> None:
    for other in db.scalars(select(Agent).where(Agent.organization_id == org_id, Agent.is_lead.is_(True))):
        if other.id != lead_id:
            other.is_lead = False


# ── 조직 ───────────────────────────────────────────────────────────────────


@router.get("/organizations", response_model=list[OrganizationSummary])
def list_organizations(db: DB) -> list[OrganizationSummary]:
    orgs = db.scalars(select(Organization).order_by(Organization.created_at)).all()
    agent_counts = dict(
        db.execute(select(Agent.organization_id, func.count()).group_by(Agent.organization_id)).all()
    )
    dept_counts = dict(
        db.execute(
            select(Department.organization_id, func.count()).group_by(Department.organization_id)
        ).all()
    )
    project_counts = dict(
        db.execute(select(Project.organization_id, func.count()).group_by(Project.organization_id)).all()
    )
    return [
        OrganizationSummary.model_validate(org).model_copy(
            update={
                "agent_count": agent_counts.get(org.id, 0),
                "department_count": dept_counts.get(org.id, 0),
                "project_count": project_counts.get(org.id, 0),
            }
        )
        for org in orgs
    ]


@router.post("/organizations", response_model=OrganizationOut, status_code=201)
def create_organization(body: OrganizationIn, db: DB) -> Organization:
    org = Organization(
        name=body.name,
        description=body.description,
        mission=body.mission,
        base_instructions=body.base_instructions,
        policy=body.policy.model_dump(),
    )
    db.add(org)
    db.flush()
    # 모든 조직은 업무 접수 창구인 CEO 한 명으로 시작한다.
    db.add(
        Agent(
            organization_id=org.id,
            name="CEO",
            title="대표",
            role="사용자의 업무 지시를 받아 분석하고 적합한 에이전트에게 분배한 뒤 결과를 보고한다.",
            is_lead=True,
            permissions=AgentPermissions(can_delegate=True).model_dump(),
        )
    )
    _log(db, org.id, "org.created", f"조직 '{org.name}' 생성")
    db.commit()
    return _load_org(db, org.id)


@router.post("/organizations/from-template", response_model=OrganizationOut, status_code=201)
def create_from_template(body: FromTemplateIn, db: DB) -> Organization:
    """템플릿을 검토 없이 바로 적용한다(빠른 시작·테스트용).

    UI는 설계 초안(/designs)을 거쳐 미리보기 후 적용한다.
    """
    template = design.get_template(body.template_key)
    if template is None:
        raise not_found("template")
    spec = template.spec if not body.name else template.spec.model_copy(update={"name": body.name})
    org, _ = design.apply_spec(db, spec, None, source=f"template:{template.template_id}@{template.version}")
    org.template_key = template.template_id
    db.commit()
    return _load_org(db, org.id)


@router.get("/organizations/{org_id}", response_model=OrganizationOut)
def get_organization(org_id: str, db: DB) -> Organization:
    return _load_org(db, org_id)


@router.patch("/organizations/{org_id}", response_model=OrganizationOut)
def update_organization(org_id: str, body: OrganizationPatch, db: DB) -> Organization:
    org = _load_org(db, org_id)
    data = body.model_dump(exclude_unset=True)
    if "policy" in data and body.policy is not None:
        data["policy"] = body.policy.model_dump()
    if data.get("default_project_id") and db.get(Project, data["default_project_id"]) is None:
        raise not_found("project")
    for key, value in data.items():
        setattr(org, key, value)
    _log(db, org.id, "org.updated", f"조직 '{org.name}' 설정 변경")
    db.commit()
    return _load_org(db, org_id)


@router.delete("/organizations/{org_id}", status_code=204)
def delete_organization(org_id: str, db: DB) -> Response:
    org = _load_org(db, org_id)
    db.delete(org)
    _log(db, None, "org.deleted", f"조직 '{org.name}' 삭제")
    db.commit()
    return Response(status_code=204)


@router.put("/organizations/{org_id}/layout", status_code=204)
def save_layout(org_id: str, body: LayoutIn, db: DB) -> Response:
    _load_org(db, org_id)
    for item in body.positions:
        agent = _agent_in_org(db, org_id, item.id)
        agent.pos_x, agent.pos_y = item.x, item.y
    db.commit()
    return Response(status_code=204)


# ── 부서 ───────────────────────────────────────────────────────────────────


@router.post("/organizations/{org_id}/departments", response_model=DepartmentOut, status_code=201)
def create_department(org_id: str, body: DepartmentIn, db: DB) -> Department:
    _load_org(db, org_id)
    dept = Department(organization_id=org_id, **body.model_dump())
    db.add(dept)
    _log(db, org_id, "department.created", f"부서 '{dept.name}' 생성")
    db.commit()
    return dept


@router.patch("/organizations/{org_id}/departments/{dept_id}", response_model=DepartmentOut)
def update_department(org_id: str, dept_id: str, body: DepartmentIn, db: DB) -> Department:
    dept = db.get(Department, dept_id)
    if dept is None or dept.organization_id != org_id:
        raise not_found("department")
    for key, value in body.model_dump().items():
        setattr(dept, key, value)
    db.commit()
    return dept


@router.delete("/organizations/{org_id}/departments/{dept_id}", status_code=204)
def delete_department(org_id: str, dept_id: str, db: DB) -> Response:
    dept = db.get(Department, dept_id)
    if dept is None or dept.organization_id != org_id:
        raise not_found("department")
    db.delete(dept)
    _log(db, org_id, "department.deleted", f"부서 '{dept.name}' 삭제")
    db.commit()
    return Response(status_code=204)


# ── 에이전트 ───────────────────────────────────────────────────────────────


@router.post("/organizations/{org_id}/agents", response_model=AgentOut, status_code=201)
def create_agent(org_id: str, body: AgentIn, db: DB) -> Agent:
    _load_org(db, org_id)
    _check_refs(db, org_id, body.department_id, body.reports_to_id, None)
    data = body.model_dump()
    data["permissions"] = body.permissions.model_dump()
    agent = Agent(organization_id=org_id, **data)
    db.add(agent)
    db.flush()
    if agent.is_lead:
        _single_lead(db, org_id, agent.id)
    _log(db, org_id, "agent.created", f"에이전트 '{agent.name}' 추가", agent.id)
    db.commit()
    return agent


@router.get("/agents/{agent_id}", response_model=AgentOut)
def get_agent(agent_id: str, db: DB) -> Agent:
    agent = db.get(Agent, agent_id)
    if agent is None:
        raise not_found("agent")
    return agent


@router.patch("/organizations/{org_id}/agents/{agent_id}", response_model=AgentOut)
def update_agent(org_id: str, agent_id: str, body: AgentPatch, db: DB) -> Agent:
    agent = _agent_in_org(db, org_id, agent_id)
    data = body.model_dump(exclude_unset=True)
    _check_refs(
        db,
        org_id,
        data.get("department_id", None) if "department_id" in data else None,
        data.get("reports_to_id", None) if "reports_to_id" in data else None,
        agent.id,
    )
    if "permissions" in data and body.permissions is not None:
        data["permissions"] = body.permissions.model_dump()
    for key, value in data.items():
        setattr(agent, key, value)
    if data.get("is_lead"):
        _single_lead(db, org_id, agent.id)
    if set(data) - {"pos_x", "pos_y"}:
        _log(db, org_id, "agent.updated", f"에이전트 '{agent.name}' 수정", agent.id)
    db.commit()
    return agent


@router.delete("/organizations/{org_id}/agents/{agent_id}", status_code=204)
def delete_agent(org_id: str, agent_id: str, db: DB) -> Response:
    agent = _agent_in_org(db, org_id, agent_id)
    # 부하 직원은 삭제된 에이전트의 상위 관리자에게 붙인다(조직도가 끊기지 않게).
    for report in db.scalars(select(Agent).where(Agent.reports_to_id == agent.id)):
        report.reports_to_id = agent.reports_to_id
    db.delete(agent)
    _log(db, org_id, "agent.deleted", f"에이전트 '{agent.name}' 삭제")
    db.commit()
    return Response(status_code=204)


# ── 협업 관계 ──────────────────────────────────────────────────────────────


@router.post("/organizations/{org_id}/collaborations", response_model=CollaborationOut, status_code=201)
def create_collaboration(org_id: str, body: CollaborationIn, db: DB) -> Collaboration:
    if body.source_agent_id == body.target_agent_id:
        raise HTTPException(422, "source and target must differ")
    _agent_in_org(db, org_id, body.source_agent_id)
    _agent_in_org(db, org_id, body.target_agent_id)
    exists = db.scalar(
        select(Collaboration).where(
            Collaboration.source_agent_id == body.source_agent_id,
            Collaboration.target_agent_id == body.target_agent_id,
            Collaboration.kind == body.kind,
        )
    )
    if exists is not None:
        raise HTTPException(409, "collaboration already exists")
    collab = Collaboration(organization_id=org_id, **body.model_dump())
    db.add(collab)
    db.commit()
    return collab


@router.delete("/organizations/{org_id}/collaborations/{collab_id}", status_code=204)
def delete_collaboration(org_id: str, collab_id: str, db: DB) -> Response:
    collab = db.get(Collaboration, collab_id)
    if collab is None or collab.organization_id != org_id:
        raise not_found("collaboration")
    db.delete(collab)
    db.commit()
    return Response(status_code=204)
