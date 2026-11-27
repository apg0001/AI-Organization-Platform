"""#95: 작업 중 보낸(대기 중인) 메시지 수정."""

from __future__ import annotations

import time
from collections.abc import Iterator
from dataclasses import replace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from ai_org.config import Settings
from ai_org.main import create_app
from ai_org.models import ChatMessage
from tests.test_chat import FakeRuntime, setup_org, wait_message


@pytest.fixture
def fake() -> FakeRuntime:
    return FakeRuntime()


@pytest.fixture
def chat(settings: Settings, fake: FakeRuntime) -> Iterator[TestClient]:
    with TestClient(
        create_app(settings, runtime_for=lambda _id: fake), base_url="http://127.0.0.1:8000"
    ) as c:
        yield c


def url(conv: dict[str, Any], mid: str, action: str = "edit-queued") -> str:
    return f"/api/v1/conversations/{conv['id']}/messages/{mid}/{action}"


def start_busy(
    chat: TestClient, conv: dict[str, Any], content: str = "대기할 것"
) -> tuple[str, dict[str, Any]]:
    """첫 메시지로 에이전트를 바쁘게 만들고, 두 번째 메시지를 대기열에 넣는다."""
    first = chat.post(f"/api/v1/conversations/{conv['id']}/messages", json={"content": "일"}).json()
    time.sleep(0.1)
    queued = chat.post(f"/api/v1/conversations/{conv['id']}/messages", json={"content": content}).json()
    assert queued["user_message"]["data"]["queue_state"] == "waiting"
    return first["assistant_message_ids"][0], queued["user_message"]


def replies(chat: TestClient, conv: dict[str, Any], count: int) -> list[dict[str, Any]]:
    deadline = time.time() + 5
    found: list[dict[str, Any]] = []
    while time.time() < deadline:
        detail = chat.get(f"/api/v1/conversations/{conv['id']}").json()
        found = [m for m in detail["messages"] if m["role"] == "assistant"]
        if len(found) >= count and all(m["status"] not in ("pending", "streaming") for m in found):
            return found
        time.sleep(0.05)
    raise AssertionError("응답이 끝나지 않았습니다")


def test_edit_queued_message_delivers_edited_content(chat: TestClient, fake: FakeRuntime) -> None:
    org, conv = setup_org(chat)
    ceo = next(a for a in org["agents"] if a["is_lead"])
    fake.queues[ceo["id"]] = [[("sleep", 0.5), ("text", "첫 작업 끝")], [("text", "반영")]]
    with chat.websocket_connect("ws://127.0.0.1:8000/api/v1/ws") as ws:
        first_id, queued = start_busy(chat, conv, "원래 내용")
        res = chat.post(url(conv, queued["id"]), json={"content": "고친 내용"})
        assert res.status_code == 200
        body = res.json()
        assert body["id"] == queued["id"] and body["content"] == "고친 내용"
        assert body["role"] == "user" and body["data"]["queue_state"] == "waiting"
        assert body["data"]["edited_at"] and body["data"]["queued"] == queued["data"]["queued"]
        assert "original_content" not in body["data"]
        while (event := ws.receive_json())["type"] != "message.status" or event.get("message_id") != queued[
            "id"
        ]:
            pass
        assert set(event) == {"type", "conversation_id", "message_id", "status", "at"}  # at: 버스 공통 시각
        assert event["conversation_id"] == conv["id"] and event["status"] == body["status"]
    wait_message(chat, conv["id"], first_id)
    assert [m["content"] for m in replies(chat, conv, 2)] == ["첫 작업 끝", "반영"]
    assert fake.requests[-1].prompt.endswith("고친 내용") and "원래 내용" not in fake.requests[-1].prompt
    detail = chat.get(f"/api/v1/conversations/{conv['id']}").json()
    stored = next(m for m in detail["messages"] if m["id"] == queued["id"])
    assert stored["content"] == "고친 내용" and stored["data"]["queue_state"] == "delivered"
    # 전달된 뒤에는 고칠 수 없다.
    assert chat.post(url(conv, queued["id"]), json={"content": "또"}).status_code == 409


def test_edit_cancelled_message_is_409(chat: TestClient, fake: FakeRuntime) -> None:
    _, conv = setup_org(chat)
    fake.script = [("sleep", 0.4), ("text", "끝")]
    first_id, queued = start_busy(chat, conv)
    assert chat.post(url(conv, queued["id"], "cancel-queued")).status_code == 200
    res = chat.post(url(conv, queued["id"]), json={"content": "고침"})
    assert res.status_code == 409 and res.json()["detail"] == "이미 전달되었거나 대기 중이 아닌 메시지입니다."
    wait_message(chat, conv["id"], first_id)


def test_edit_rejects_wrong_targets_and_bad_content(chat: TestClient, fake: FakeRuntime) -> None:
    org, conv = setup_org(chat)
    other = chat.post("/api/v1/conversations", json={"organization_id": org["id"]}).json()
    fake.script = [("sleep", 0.4), ("text", "끝")]
    first_id, queued = start_busy(chat, conv)
    # 다른 대화의 경로로는 404, 없는 메시지도 404.
    assert chat.post(url(other, queued["id"]), json={"content": "x"}).status_code == 404
    assert chat.post(url(conv, "nope"), json={"content": "x"}).status_code == 404
    # assistant 메시지는 404(사용자 메시지만 대상).
    assert chat.post(url(conv, first_id), json={"content": "x"}).status_code == 404
    # 내용 규칙은 새 메시지와 같다.
    assert chat.post(url(conv, queued["id"]), json={"content": ""}).status_code == 422
    assert chat.post(url(conv, queued["id"]), json={}).status_code == 422
    assert chat.post(url(conv, queued["id"]), json={"content": "x" * 50_001}).status_code == 422
    # 대기 중이 아닌 일반 user 메시지는 409.
    detail = chat.get(f"/api/v1/conversations/{conv['id']}").json()
    plain = next(m for m in detail["messages"] if m["role"] == "user" and m["id"] != queued["id"])
    assert chat.post(url(conv, plain["id"]), json={"content": "x"}).status_code == 409
    # 수정은 내용만 바꾼다: 상태·대상은 그대로.
    stored = next(m for m in detail["messages"] if m["id"] == queued["id"])
    assert stored["content"] == "대기할 것" and stored["data"]["queue_state"] == "waiting"
    wait_message(chat, conv["id"], first_id)


def test_edit_after_delivery_started_is_409(chat: TestClient, fake: FakeRuntime) -> None:
    """전달(deliver_queued)이 먼저 일어나면 수정은 409, 수정이 먼저면 수정된 내용이 전달된다."""
    org, conv = setup_org(chat)
    ceo = next(a for a in org["agents"] if a["is_lead"])
    fake.queues[ceo["id"]] = [[("sleep", 0.3), ("text", "첫")], [("sleep", 0.3), ("text", "둘")]]
    first_id, queued = start_busy(chat, conv, "원문")
    manager = chat.app.state.runs  # type: ignore[attr-defined]
    wait_message(chat, conv["id"], first_id)
    deadline = time.time() + 3
    while time.time() < deadline and len(fake.requests) < 2:
        time.sleep(0.02)
    assert fake.requests[-1].prompt == "원문"
    assert manager.edit_queued(conv["id"], queued["id"], "늦은 수정") is None
    assert chat.post(url(conv, queued["id"]), json={"content": "늦은 수정"}).status_code == 409
    replies(chat, conv, 2)


def test_stop_and_restart_still_cancel_edited_messages(chat: TestClient, fake: FakeRuntime) -> None:
    _, conv = setup_org(chat)
    fake.script = [("sleep", 0.5), ("text", "끝")]
    first_id, queued = start_busy(chat, conv)
    assert chat.post(url(conv, queued["id"]), json={"content": "고침"}).status_code == 200
    assert chat.post(f"/api/v1/conversations/{conv['id']}/stop").status_code == 200
    wait_message(chat, conv["id"], first_id)
    detail = chat.get(f"/api/v1/conversations/{conv['id']}").json()
    stored = next(m for m in detail["messages"] if m["id"] == queued["id"])
    assert stored["data"]["queue_state"] == "cancelled" and stored["content"] == "고침"
    # 재시작 복구도 edited_at이 있는 대기 메시지를 그대로 취소한다.
    manager = chat.app.state.runs  # type: ignore[attr-defined]
    with manager.factory() as db:
        msg = db.get(ChatMessage, queued["id"])
        msg.data = {**msg.data, "queue_state": "waiting", "queued": queued["data"]["queued"]}
        db.commit()
    manager.recover()
    detail = chat.get(f"/api/v1/conversations/{conv['id']}").json()
    stored = next(m for m in detail["messages"] if m["id"] == queued["id"])
    assert stored["data"]["queue_state"] == "cancelled" and stored["data"]["edited_at"]


def test_edit_queued_requires_login(settings: Settings) -> None:
    with TestClient(
        create_app(replace(settings, auth_enabled=True)), base_url="http://127.0.0.1:8000"
    ) as api:
        res = api.post("/api/v1/conversations/x/messages/y/edit-queued", json={"content": "a"})
        assert res.status_code == 401
        res = api.post(
            "/api/v1/conversations/x/messages/y/edit-queued",
            json={"content": "a"},
            headers={"origin": "https://evil.example"},
        )
        assert res.status_code == 403


def test_edit_blocked_once_any_agent_received(chat: TestClient, fake: FakeRuntime) -> None:
    """여러 에이전트 대기: 한 에이전트가 먼저 받으면 수정 409, 나머지는 원래 내용을 받는다(R1)."""
    org, conv = setup_org(chat)
    ceo = next(a for a in org["agents"] if a["is_lead"])
    dev = next(a for a in org["agents"] if a["name"] == "백엔드 개발자")
    fake.queues[ceo["id"]] = [[("sleep", 0.2), ("text", "CEO 첫")], [("text", "CEO 둘")]]
    fake.queues[dev["id"]] = [[("sleep", 0.9), ("text", "개발 첫")], [("text", "개발 둘")]]
    messages = f"/api/v1/conversations/{conv['id']}/messages"
    chat.post(messages, json={"content": "CEO 일", "mention_agent_ids": [ceo["id"]]})
    chat.post(messages, json={"content": "개발 일", "mention_agent_ids": [dev["id"]]})
    time.sleep(0.1)
    both = chat.post(
        messages, json={"content": "원래 내용", "mention_agent_ids": [ceo["id"], dev["id"]]}
    ).json()
    queued = both["user_message"]
    assert set(both["queued_agent_ids"]) == {ceo["id"], dev["id"]}
    assert "delivered_agent_ids" not in queued["data"]
    # CEO가 먼저 끝나 대기 메시지를 받는다.
    deadline = time.time() + 3
    while time.time() < deadline and not any(r.prompt == "원래 내용" for r in fake.requests):
        time.sleep(0.02)
    detail = chat.get(f"/api/v1/conversations/{conv['id']}").json()
    stored = next(m for m in detail["messages"] if m["id"] == queued["id"])
    assert stored["data"]["queue_state"] == "waiting" and stored["data"]["delivered_agent_ids"] == [ceo["id"]]
    res = chat.post(url(conv, queued["id"]), json={"content": "고친 내용"})
    assert res.status_code == 409 and res.json()["detail"] == "이미 전달되었거나 대기 중이 아닌 메시지입니다."
    replies(chat, conv, 4)
    delivered = [r for r in fake.requests if r.prompt in ("원래 내용", "고친 내용")]
    assert [(r.agent_id, r.prompt) for r in delivered] == [(ceo["id"], "원래 내용"), (dev["id"], "원래 내용")]
    detail = chat.get(f"/api/v1/conversations/{conv['id']}").json()
    stored = next(m for m in detail["messages"] if m["id"] == queued["id"])
    assert stored["data"]["queue_state"] == "delivered"
    assert stored["data"]["delivered_agent_ids"] == [ceo["id"], dev["id"]]


def test_edit_blocked_when_some_targets_received_immediately(chat: TestClient, fake: FakeRuntime) -> None:
    """한 대상은 바쁘고 다른 대상은 바로 받은 메시지도 수정할 수 없다."""
    org, conv = setup_org(chat)
    ceo = next(a for a in org["agents"] if a["is_lead"])
    dev = next(a for a in org["agents"] if a["name"] == "백엔드 개발자")
    fake.queues[ceo["id"]] = [[("sleep", 0.4), ("text", "CEO 첫")], [("text", "CEO 둘")]]
    messages = f"/api/v1/conversations/{conv['id']}/messages"
    chat.post(messages, json={"content": "CEO 일", "mention_agent_ids": [ceo["id"]]})
    time.sleep(0.1)
    both = chat.post(
        messages, json={"content": "원래 내용", "mention_agent_ids": [ceo["id"], dev["id"]]}
    ).json()
    assert both["queued_agent_ids"] == [ceo["id"]] and len(both["assistant_message_ids"]) == 1
    queued = both["user_message"]
    assert queued["data"]["delivered_agent_ids"] == [dev["id"]]
    assert chat.post(url(conv, queued["id"]), json={"content": "고침"}).status_code == 409
    replies(chat, conv, 3)
    assert [r.prompt for r in fake.requests if r.agent_id == ceo["id"]][-1] == "원래 내용"
