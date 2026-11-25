"""조직 설계(Organization Builder) API — 설계 모드.

초안(OrgDesign) 하나가 대화·조직도·검토 화면의 단일 상태다. 적용 전까지 실제 조직은 바뀌지 않는다.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select

from ai_org.deps import DB, AppSettings, not_found
from ai_org.models import Organization, OrgDesign, OrgRevision, Project
from ai_org.runtime.base import PermissionDecision, RunRequest
from ai_org.services import design as svc
from ai_org.services.capabilities import discover_all
from ai_org.services.runs import RunManager
from ai_org.spec import OrgSpec

router = APIRouter(prefix="/api/v1", tags=["organization-builder"])


class DesignIn(BaseModel):
    organization_id: str | None = None
    template_id: str | None = None
    name: str | None = Field(default=None, max_length=120)


class SpecIn(BaseModel):
    spec: OrgSpec
    note: str = Field(default="", max_length=300)


class DesignMessageIn(BaseModel):
    content: str = Field(min_length=1, max_length=8000)


class ApplyIn(BaseModel):
    confirm_running: bool = False


def _runs(request: Request) -> RunManager:
    manager: RunManager = request.app.state.runs
    return manager


def _caps(db: DB, settings: AppSettings) -> list[Any]:
    return discover_all(settings.claude_home, list(db.scalars(select(Project.path))))


def _design_json(d: OrgDesign, db: DB, settings: AppSettings) -> dict[str, Any]:
    spec = OrgSpec.model_validate(d.spec)
    return {
        "id": d.id,
        "organization_id": d.organization_id,
        "origin": d.origin,
        "status": d.status,
        "busy": d.busy,
        "spec": d.spec,
        "messages": d.messages,
        "notes": d.notes,
        "recommendations": svc.recommendation_status(spec, _caps(db, settings)),
        "updated_at": d.updated_at.isoformat(),
    }


def _get(db: DB, design_id: str) -> OrgDesign:
    d = db.get(OrgDesign, design_id)
    if d is None:
        raise not_found("design")
    return d


def _editable(d: OrgDesign) -> None:
    if d.status != "draft":
        raise HTTPException(409, "이미 적용했거나 버린 설계입니다. 새 설계를 시작하세요.")


def _publish(request: Request, d: OrgDesign) -> None:
    _runs(request).bus.publish("design.updated", design_id=d.id, status=d.status, busy=d.busy)


# ── 템플릿 ─────────────────────────────────────────────────────────────────


@router.get("/templates")
def list_templates() -> list[dict[str, Any]]:
    return [t.model_dump(mode="json") for t in svc.load_templates()]


# ── 설계 초안 ──────────────────────────────────────────────────────────────


@router.post("/designs", status_code=201)
def create_design(body: DesignIn, db: DB, settings: AppSettings) -> dict[str, Any]:
    if body.organization_id:
        org = db.get(Organization, body.organization_id)
        if org is None:
            raise not_found("organization")
        spec, origin = svc.org_to_spec(db, org), "org"
    elif body.template_id:
        template = svc.get_template(body.template_id)
        if template is None:
            raise not_found("template")
        spec, origin = template.spec, f"template:{template.template_id}@{template.version}"
    else:
        spec, origin = svc.blank_spec(), "blank"
    if body.name:
        spec = spec.model_copy(update={"name": body.name})
    d = OrgDesign(
        organization_id=body.organization_id, origin=origin, spec=spec.model_dump(mode="json"), messages=[]
    )
    db.add(d)
    db.commit()
    return _design_json(d, db, settings)


@router.get("/designs")
def list_designs(db: DB, organization_id: str | None = None) -> list[dict[str, Any]]:
    query = select(OrgDesign).where(OrgDesign.status == "draft").order_by(OrgDesign.updated_at.desc())
    if organization_id:
        query = query.where(OrgDesign.organization_id == organization_id)
    return [
        {
            "id": d.id,
            "organization_id": d.organization_id,
            "origin": d.origin,
            "name": d.spec.get("name"),
            "updated_at": d.updated_at.isoformat(),
        }
        for d in db.scalars(query)
    ]


@router.get("/designs/{design_id}")
def get_design(design_id: str, db: DB, settings: AppSettings) -> dict[str, Any]:
    return _design_json(_get(db, design_id), db, settings)


@router.put("/designs/{design_id}/spec")
def put_spec(design_id: str, body: SpecIn, db: DB, settings: AppSettings, request: Request) -> dict[str, Any]:
    """조직도·폼에서 직접 고친 명세. 사용자 편집이므로 권한 변경도 그대로 반영한다."""
    d = _get(db, design_id)
    _editable(d)
    before = OrgSpec.model_validate(d.spec)
    d.spec = body.spec.model_dump(mode="json")
    changes = svc.summarize_diff(before, body.spec)
    if changes != ["변경 없음"]:
        d.messages = [
            *d.messages,
            {
                "role": "edit",
                "content": body.note or "조직도에서 직접 수정",
                "changes": changes,
                "at": _now(),
            },
        ]
    db.commit()
    _publish(request, d)
    return _design_json(d, db, settings)


@router.post("/designs/{design_id}/accept-permissions/{agent_key}")
def accept_permission_suggestion(
    design_id: str, agent_key: str, db: DB, settings: AppSettings, request: Request
) -> dict[str, Any]:
    """AI가 제안한 권한 확대를 사용자가 명시적으로 수락한다."""
    d = _get(db, design_id)
    _editable(d)
    spec = OrgSpec.model_validate(d.spec)
    agents = []
    found = False
    for a in spec.agents:
        if a.key == agent_key and a.permission_suggestion is not None:
            a = a.model_copy(update={"permissions": a.permission_suggestion, "permission_suggestion": None})
            found = True
        agents.append(a)
    if not found:
        raise not_found("permission suggestion")
    d.spec = spec.model_copy(update={"agents": agents}).model_dump(mode="json")
    db.commit()
    _publish(request, d)
    return _design_json(d, db, settings)


@router.delete("/designs/{design_id}", status_code=204)
def discard_design(design_id: str, db: DB) -> Response:
    d = _get(db, design_id)
    d.status = "discarded"
    db.commit()
    return Response(status_code=204)


# ── 설계 대화 ──────────────────────────────────────────────────────────────


@router.post("/designs/{design_id}/messages", status_code=202)
async def design_message(
    design_id: str, body: DesignMessageIn, db: DB, settings: AppSettings, request: Request
) -> dict[str, Any]:
    d = _get(db, design_id)
    _editable(d)
    if d.busy:
        raise HTTPException(409, "설계 담당자가 아직 답하는 중입니다.")
    d.messages = [*d.messages, {"role": "user", "content": body.content, "at": _now()}]
    d.busy = True
    db.commit()
    _publish(request, d)
    spec = OrgSpec.model_validate(d.spec)
    prompt = svc.designer_prompt(spec, body.content, svc.load_templates(), _caps(db, settings))
    workspace = settings.home / "designer"
    workspace.mkdir(parents=True, exist_ok=True, mode=0o700)
    run_request = RunRequest(
        agent_id=f"designer:{d.id}",
        prompt=prompt,
        cwd=workspace,
        system_prompt=svc.DESIGNER_SYSTEM,
        tools=(),
        output_schema=svc.designer_schema(),
        resume_session_id=d.designer_session_id,
        max_turns=4,
        setting_sources=(),
    )
    manager = _runs(request)
    task = asyncio.create_task(_run_designer(manager, d.id, run_request))
    request.app.state.design_tasks.add(task)
    task.add_done_callback(request.app.state.design_tasks.discard)
    return {"status": "accepted"}


# Claude Code는 구조화 출력을 내부 도구 StructuredOutput 호출로 전달한다(실측: 막으면 결과를 못 받음).
STRUCTURED_OUTPUT_TOOL = "StructuredOutput"


async def _designer_permission(tool: str, _input: dict[str, Any]) -> PermissionDecision:
    if tool == STRUCTURED_OUTPUT_TOOL:
        return PermissionDecision(True)
    return PermissionDecision(
        False, "설계 담당자는 도구를 쓰지 않습니다. 결과는 StructuredOutput으로만 내세요."
    )


async def _run_designer(manager: RunManager, design_id: str, request: RunRequest) -> None:
    result: dict[str, Any] = {}
    error: str | None = None
    try:
        async with manager.limit:
            handle = manager.runtime_for("claude-code").start(request, _designer_permission)
            async for ev in handle.events():
                if ev.type == "turn.completed":
                    result = ev.data
                elif ev.type == "error":
                    error = ev.data.get("message")
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"[:300]
    with manager.factory() as db:
        d = db.get(OrgDesign, design_id)
        if d is None:
            return
        d.busy = False
        if result.get("session_id"):
            d.designer_session_id = result["session_id"]
        output = result.get("structured_output")
        message: dict[str, Any] = {"role": "designer", "at": _now()}
        if error or not isinstance(output, dict):
            message["error"] = error or "설계 담당자가 구조화된 답을 주지 않았습니다. 다시 시도하세요."
            message["content"] = result.get("result") or ""
        else:
            message["content"] = str(output.get("reply") or "")
            message["questions"] = [str(q) for q in output.get("questions") or []][:3]
            if output.get("spec"):
                current = OrgSpec.model_validate(d.spec)
                try:
                    proposal = OrgSpec.model_validate(output["spec"])
                except ValidationError as exc:
                    message["error"] = (
                        f"제안한 조직 구조가 올바르지 않아 반영하지 않았습니다: {exc.errors()[0]['msg']}"
                    )
                else:
                    safe, notes = svc.sanitize_proposal(proposal, current)
                    message["changes"] = svc.summarize_diff(current, safe)
                    message["notes"] = notes
                    d.spec = safe.model_dump(mode="json")
                    d.notes = notes
        d.messages = [*d.messages, message]
        d.updated_at = datetime.now(UTC)
        db.commit()
        manager.bus.publish("design.updated", design_id=d.id, status=d.status, busy=False)


# ── 적용·이력 ──────────────────────────────────────────────────────────────


@router.post("/designs/{design_id}/apply")
def apply_design(design_id: str, body: ApplyIn, db: DB, request: Request) -> dict[str, Any]:
    d = _get(db, design_id)
    _editable(d)
    if d.busy:
        raise HTTPException(409, "설계 담당자가 답하는 중에는 적용할 수 없습니다.")
    spec = OrgSpec.model_validate(d.spec)
    org = db.get(Organization, d.organization_id) if d.organization_id else None
    if d.organization_id and org is None:
        raise not_found("organization")
    if org is not None:
        manager = _runs(request)
        busy_agents = {r.agent_id for r in manager.runs.values()}
        keep = {a.key for a in spec.agents}
        affected = [a for a in busy_agents if manager._org_of(a) == org.id]
        if affected and not body.confirm_running:
            removed = [a for a in affected if a not in keep]
            raise HTTPException(
                409,
                {
                    "message": "실행 중인 작업이 있습니다. 적용하면 에이전트 설정이 다음 턴부터 바뀝니다"
                    + (" (삭제되는 에이전트의 실행은 중지됩니다)." if removed else "."),
                    "running_agent_ids": affected,
                },
            )
    org, changes = svc.apply_spec(db, spec, org, source=f"design:{d.id}")
    d.organization_id, d.status = org.id, "applied"
    db.commit()
    _runs(request).bus.publish("organization.updated", organization_id=org.id)
    return {"organization_id": org.id, "changes": changes}


@router.get("/organizations/{org_id}/revisions")
def list_revisions(org_id: str, db: DB) -> list[dict[str, Any]]:
    return [
        {
            "id": r.id,
            "summary": r.summary,
            "source": r.source,
            "created_at": r.created_at.isoformat(),
            "agent_count": len(r.spec.get("agents", [])),
        }
        for r in db.scalars(
            select(OrgRevision)
            .where(OrgRevision.organization_id == org_id)
            .order_by(OrgRevision.created_at.desc())
        )
    ]


@router.post("/organizations/{org_id}/revisions/{revision_id}/restore", status_code=201)
def restore_revision(org_id: str, revision_id: str, db: DB, settings: AppSettings) -> dict[str, Any]:
    """이전 구성으로 되돌리는 설계 초안을 만든다(미리보기 후 사용자가 적용)."""
    rev = db.get(OrgRevision, revision_id)
    if rev is None or rev.organization_id != org_id:
        raise not_found("revision")
    current = svc.org_to_spec(db, db.get(Organization, org_id))  # type: ignore[arg-type]
    restored = OrgSpec.model_validate(rev.spec)
    # 삭제된 뒤 다시 만들어지는 에이전트는 새 ID를 받는다(이전 대화·세션은 이어지지 않는다).
    d = OrgDesign(
        organization_id=org_id,
        origin=f"revision:{rev.id}",
        spec=restored.model_dump(mode="json"),
        messages=[
            {
                "role": "edit",
                "content": "이전 구성으로 되돌리기",
                "changes": svc.summarize_diff(current, restored),
                "at": _now(),
            }
        ],
    )
    db.add(d)
    db.commit()
    return _design_json(d, db, settings)


def _now() -> str:
    return datetime.now(UTC).isoformat()
