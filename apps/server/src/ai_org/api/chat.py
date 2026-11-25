"""채팅 API: 대화·메시지·슬래시 명령·첨부·승인·작업, 그리고 실시간 WebSocket."""

from __future__ import annotations

import asyncio
import contextlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, HTTPException, Request, Response, UploadFile, WebSocket
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from starlette.websockets import WebSocketDisconnect

from ai_org.deps import DB, AppSettings, not_found
from ai_org.models import (
    Agent,
    Approval,
    Attachment,
    ChatMessage,
    Conversation,
    Department,
    Organization,
    Project,
    Task,
)
from ai_org.schemas import ApprovalOut, TaskOut
from ai_org.security import _host_name
from ai_org.services import attachments as att
from ai_org.services.commands import REGISTRY, CommandContext, CommandError, execute
from ai_org.services.runs import RouteError, RunManager, message_json, resolve_routes, validate_context

router = APIRouter(prefix="/api/v1", tags=["chat"])


class ContextItem(BaseModel):
    kind: str = Field(pattern="^(path|agent|task|github|capability)$")
    ref: str = Field(min_length=1, max_length=500)
    label: str = Field(default="", max_length=200)


class ConversationIn(BaseModel):
    organization_id: str
    target_kind: str = Field(default="org", pattern="^(org|team|agent)$")
    target_id: str | None = None
    project_id: str | None = None
    title: str | None = Field(default=None, max_length=200)


class ConversationPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    target_kind: str | None = Field(default=None, pattern="^(org|team|agent)$")
    target_id: str | None = None
    project_id: str | None = None
    context: list[ContextItem] | None = None
    archived: bool | None = None


class MessageIn(BaseModel):
    content: str = Field(min_length=1, max_length=50_000)
    mention_agent_ids: list[str] = Field(default_factory=list, max_length=10)
    mention_all: bool = False
    attachment_ids: list[str] = Field(default_factory=list, max_length=att.MAX_FILES_PER_MESSAGE)


class CommandIn(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    args: dict[str, str] = Field(default_factory=dict)


class DecisionIn(BaseModel):
    allow: bool


def runs_of(request: Request) -> RunManager:
    manager: RunManager = request.app.state.runs
    return manager


def _conv_json(conv: Conversation, busy: bool) -> dict[str, Any]:
    return {
        "id": conv.id,
        "organization_id": conv.organization_id,
        "target_kind": conv.target_kind,
        "target_id": conv.target_id,
        "project_id": conv.project_id,
        "title": conv.title,
        "context": conv.context or [],
        "archived": conv.archived,
        "busy": busy,
        "created_at": conv.created_at.isoformat(),
        "updated_at": conv.updated_at.isoformat(),
    }


def _get_conv(db: DB, conv_id: str) -> Conversation:
    conv = db.get(Conversation, conv_id)
    if conv is None:
        raise not_found("conversation")
    return conv


def _check_target(db: DB, org_id: str, kind: str, target_id: str | None) -> None:
    if kind == "org":
        return
    if target_id is None:
        raise HTTPException(422, "target_id required")
    row: Agent | Department | None = (
        db.get(Agent, target_id) if kind == "agent" else db.get(Department, target_id)
    )
    if row is None or row.organization_id != org_id:
        raise not_found(kind)


# ── 대화 ───────────────────────────────────────────────────────────────────


@router.get("/conversations")
def list_conversations(
    db: DB, request: Request, organization_id: str, archived: bool = False
) -> list[dict[str, Any]]:
    runs = runs_of(request)
    convs = db.scalars(
        select(Conversation)
        .where(Conversation.organization_id == organization_id, Conversation.archived.is_(archived))
        .order_by(Conversation.updated_at.desc())
    )
    return [_conv_json(c, runs.is_busy(c.id)) for c in convs]


@router.post("/conversations", status_code=201)
def create_conversation(body: ConversationIn, db: DB, request: Request) -> dict[str, Any]:
    if db.get(Organization, body.organization_id) is None:
        raise not_found("organization")
    _check_target(db, body.organization_id, body.target_kind, body.target_id)
    if body.project_id and db.get(Project, body.project_id) is None:
        raise not_found("project")
    conv = Conversation(
        organization_id=body.organization_id,
        target_kind=body.target_kind,
        target_id=body.target_id if body.target_kind != "org" else None,
        project_id=body.project_id,
        title=body.title or "새 대화",
    )
    db.add(conv)
    db.commit()
    return _conv_json(conv, False)


@router.get("/conversations/{conv_id}")
def get_conversation(conv_id: str, db: DB, request: Request) -> dict[str, Any]:
    conv = _get_conv(db, conv_id)
    messages = db.scalars(
        select(ChatMessage).where(ChatMessage.conversation_id == conv.id).order_by(ChatMessage.created_at)
    )
    attachments = {
        a.id: a for a in db.scalars(select(Attachment).where(Attachment.conversation_id == conv.id))
    }
    out = _conv_json(conv, runs_of(request).is_busy(conv.id))
    out["messages"] = [message_json(m) for m in messages]
    out["attachments"] = [_attachment_json(a) for a in attachments.values()]
    return out


@router.patch("/conversations/{conv_id}")
def update_conversation(conv_id: str, body: ConversationPatch, db: DB, request: Request) -> dict[str, Any]:
    conv = _get_conv(db, conv_id)
    data = body.model_dump(exclude_unset=True)
    if "target_kind" in data:
        kind = data["target_kind"]
        target = data.get("target_id")
        _check_target(db, conv.organization_id, kind, target)
        conv.target_kind, conv.target_id = kind, target if kind != "org" else None
    if "project_id" in data:
        if data["project_id"] and db.get(Project, data["project_id"]) is None:
            raise not_found("project")
        conv.project_id = data["project_id"]
    if "context" in data and body.context is not None:
        items = [c.model_dump() for c in body.context]
        try:
            validate_context(db, conv, items)
        except RouteError as exc:
            raise HTTPException(422, str(exc)) from exc
        conv.context = items
    if body.title is not None:
        conv.title = body.title
    if body.archived is not None:
        conv.archived = body.archived
    db.commit()
    return _conv_json(conv, runs_of(request).is_busy(conv.id))


@router.delete("/conversations/{conv_id}", status_code=204)
async def delete_conversation(conv_id: str, db: DB, request: Request, settings: AppSettings) -> Response:
    conv = _get_conv(db, conv_id)
    await runs_of(request).stop(conversation_id=conv.id)
    for a in db.scalars(select(Attachment).where(Attachment.conversation_id == conv.id)):
        att.remove(a.stored_path, settings.upload_root)
    db.delete(conv)
    db.commit()
    return Response(status_code=204)


# ── 메시지 ─────────────────────────────────────────────────────────────────


@router.post("/conversations/{conv_id}/messages", status_code=202)
async def send_message(conv_id: str, body: MessageIn, db: DB, request: Request) -> dict[str, Any]:
    conv = _get_conv(db, conv_id)
    runs = runs_of(request)
    files: list[Attachment] = []
    for attachment_id in body.attachment_ids:
        a = db.get(Attachment, attachment_id)
        if a is None or a.conversation_id is not None:
            raise not_found("attachment")
        a.conversation_id = conv.id
        files.append(a)
    try:
        routes = resolve_routes(db, conv, body.mention_agent_ids, body.mention_all)
        validate_context(db, conv, conv.context or [])
    except RouteError as exc:
        raise HTTPException(422, str(exc)) from exc
    busy = {r.agent_id for r in runs.runs.values() if r.conversation_id == conv.id}
    if any(route.agent.id in busy for route in routes):
        raise HTTPException(
            409, "이 대화에서 해당 에이전트가 아직 응답 중입니다. 중지하거나 끝날 때까지 기다리세요."
        )
    user = ChatMessage(
        conversation_id=conv.id,
        role="user",
        content=body.content,
        data={
            "mentions": [r.agent.id for r in routes] if (body.mention_agent_ids or body.mention_all) else [],
            "mention_all": body.mention_all,
            "attachments": [_attachment_json(a) for a in files],
        },
    )
    db.add(user)
    if conv.title == "새 대화":
        conv.title = " ".join(body.content.split())[:60]
    conv.updated_at = datetime.now(UTC)
    db.commit()
    runs.bus.publish("message.created", conversation_id=conv.id, message=message_json(user))
    replies = [runs.launch(db, conv, route, body.content, files) for route in routes]
    return {"user_message": message_json(user), "assistant_message_ids": [m.id for m in replies]}


@router.post("/conversations/{conv_id}/messages/{message_id}/regenerate", status_code=202)
async def regenerate(conv_id: str, message_id: str, db: DB, request: Request) -> dict[str, Any]:
    conv = _get_conv(db, conv_id)
    target = db.get(ChatMessage, message_id)
    if (
        target is None
        or target.conversation_id != conv.id
        or target.role != "assistant"
        or not target.agent_id
    ):
        raise not_found("message")
    runs = runs_of(request)
    if runs.is_busy(conv.id):
        raise HTTPException(409, "실행 중인 응답이 있습니다.")
    prompt_msg = db.scalar(
        select(ChatMessage)
        .where(
            ChatMessage.conversation_id == conv.id,
            ChatMessage.role == "user",
            ChatMessage.created_at <= target.created_at,
        )
        .order_by(ChatMessage.created_at.desc())
    )
    agent = db.get(Agent, target.agent_id)
    if prompt_msg is None or agent is None:
        raise HTTPException(422, "다시 생성할 원래 질문을 찾을 수 없습니다.")
    files = [
        a
        for a in (db.get(Attachment, x["id"]) for x in (prompt_msg.data or {}).get("attachments", []))
        if a is not None
    ]
    from ai_org.services.runs import Route

    scope = "org" if agent.is_lead and conv.target_kind == "org" else "agent"
    reply = runs.launch(db, conv, Route(agent, scope), prompt_msg.content, files)
    return {"assistant_message_ids": [reply.id]}


@router.post("/conversations/{conv_id}/stop")
async def stop_conversation(conv_id: str, db: DB, request: Request) -> dict[str, int]:
    _get_conv(db, conv_id)
    return {"stopped": await runs_of(request).stop(conversation_id=conv_id)}


# ── 명령 ───────────────────────────────────────────────────────────────────


@router.get("/commands")
def list_commands() -> list[dict[str, Any]]:
    return [c.spec() for c in REGISTRY.values()]


@router.post("/conversations/{conv_id}/commands")
async def run_command(
    conv_id: str, body: CommandIn, db: DB, request: Request, settings: AppSettings
) -> dict[str, Any]:
    conv = _get_conv(db, conv_id)
    runs = runs_of(request)
    ctx = CommandContext(
        db=db, conversation=conv, args=body.args, runs=runs, claude_home=settings.claude_home
    )
    invocation = "/" + body.name + ("" if not body.args else " " + " ".join(body.args.values()))
    try:
        result = await execute(body.name, ctx)
        data: dict[str, Any] = {"command": body.name, "result": result.to_dict()}
        error = None
    except CommandError as exc:
        data, error = {"command": body.name}, str(exc)
    msg = ChatMessage(
        conversation_id=conv.id,
        role="command",
        content=invocation,
        data=data,
        status="error" if error else "done",
        error=error,
    )
    db.add(msg)
    db.commit()
    runs.bus.publish("message.created", conversation_id=conv.id, message=message_json(msg))
    return message_json(msg)


# ── 첨부 ───────────────────────────────────────────────────────────────────


def _attachment_json(a: Attachment) -> dict[str, Any]:
    return {
        "id": a.id,
        "filename": a.filename,
        "media_type": a.media_type,
        "size": a.size,
        "conversation_id": a.conversation_id,
    }


@router.post("/attachments", status_code=201)
async def upload(db: DB, settings: AppSettings, file: UploadFile = File(...)) -> dict[str, Any]:  # noqa: B008
    """초안 첨부. 메시지를 보낼 때 대화에 묶인다. 묶이지 않은 초안은 24시간 뒤 정리한다."""
    chunks: list[bytes] = []
    size = 0
    while chunk := await file.read(1024 * 1024):
        size += len(chunk)
        if size > att.MAX_FILE_BYTES:
            raise HTTPException(413, f"파일은 {att.MAX_FILE_BYTES // (1024 * 1024)}MB까지 올릴 수 있습니다.")
        chunks.append(chunk)
    if size == 0:
        raise HTTPException(422, "빈 파일입니다.")
    try:
        checked = att.check(file.filename or "file", b"".join(chunks)[:4096])
    except att.AttachmentError as exc:
        raise HTTPException(415, str(exc)) from exc
    record = Attachment(
        filename=checked.filename, media_type=checked.media_type, size=0, sha256="", stored_path=""
    )
    db.add(record)
    db.flush()
    path, stored_size, digest = att.store(settings.upload_root, record.id, checked, chunks)
    record.size, record.sha256, record.stored_path = stored_size, digest, str(path)
    db.commit()
    return _attachment_json(record)


@router.get("/attachments/{attachment_id}/content")
def attachment_content(attachment_id: str, db: DB) -> FileResponse:
    a = db.get(Attachment, attachment_id)
    if a is None or not Path(a.stored_path).is_file():
        raise not_found("attachment")
    return FileResponse(
        a.stored_path, media_type=a.media_type, filename=a.filename, content_disposition_type="inline"
    )


@router.delete("/attachments/{attachment_id}", status_code=204)
def delete_attachment(attachment_id: str, db: DB, settings: AppSettings) -> Response:
    a = db.get(Attachment, attachment_id)
    if a is None:
        raise not_found("attachment")
    if a.conversation_id is not None:
        raise HTTPException(
            409, "이미 보낸 메시지의 첨부는 삭제할 수 없습니다. 대화를 삭제하면 함께 지워집니다."
        )
    att.remove(a.stored_path, settings.upload_root)
    db.delete(a)
    db.commit()
    return Response(status_code=204)


# ── 승인·작업 ──────────────────────────────────────────────────────────────


@router.get("/approvals", response_model=list[ApprovalOut])
def list_approvals(db: DB, organization_id: str | None = None, status: str = "pending") -> list[Approval]:
    query = select(Approval).where(Approval.status == status).order_by(Approval.created_at)
    if organization_id:
        query = query.where(Approval.organization_id == organization_id)
    return list(db.scalars(query))


@router.post("/approvals/{approval_id}/decision")
def decide(approval_id: str, body: DecisionIn, db: DB, request: Request) -> dict[str, str]:
    approval = db.get(Approval, approval_id)
    if approval is None:
        raise not_found("approval")
    if not runs_of(request).decide(approval_id, body.allow):
        raise HTTPException(409, "이미 처리되었거나 만료된 요청입니다.")
    return {"status": "approved" if body.allow else "denied"}


@router.get("/tasks", response_model=list[TaskOut])
def list_tasks(db: DB, organization_id: str) -> list[Task]:
    return list(
        db.scalars(
            select(Task)
            .where(Task.organization_id == organization_id)
            .order_by(Task.updated_at.desc())
            .limit(100)
        )
    )


@router.get("/runs")
def active_runs(request: Request) -> list[dict[str, Any]]:
    return [
        {"message_id": r.message_id, "conversation_id": r.conversation_id, "agent_id": r.agent_id}
        for r in runs_of(request).runs.values()
    ]


# ── 실시간 ─────────────────────────────────────────────────────────────────


@router.websocket("/ws")
async def live(websocket: WebSocket) -> None:
    settings = websocket.app.state.settings
    host = _host_name(websocket.headers.get("host", ""))
    origin = websocket.headers.get("origin")
    if host not in settings.allowed_hosts or (origin is not None and origin not in settings.allowed_origins):
        await websocket.close(code=4403)
        return
    if settings.auth_enabled:
        from ai_org.services import auth

        with websocket.app.state.session_factory() as db:
            user = auth.user_for_token(db, websocket.cookies.get(auth.COOKIE))
        if user is None:
            await websocket.close(code=4401)
            return
    await websocket.accept()
    bus = websocket.app.state.runs.bus
    with bus.subscribe() as queue:
        receiver = asyncio.create_task(_drain(websocket))
        try:
            while not receiver.done():
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=25)
                except TimeoutError:
                    event = {"type": "ping"}
                await websocket.send_json(event)
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            receiver.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await receiver


async def _drain(websocket: WebSocket) -> None:
    """클라이언트 메시지는 쓰지 않는다(연결 종료 감지용)."""
    with contextlib.suppress(WebSocketDisconnect):
        while True:
            await websocket.receive_text()
