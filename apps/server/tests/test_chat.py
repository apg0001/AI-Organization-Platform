from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from ai_org.config import Settings
from ai_org.main import create_app
from ai_org.runtime.base import PermissionCallback, RunRequest, RuntimeEvent


class FakeRun:
    """스크립트대로 이벤트를 내는 가짜 런타임. tool 단계에서 실제처럼 권한 콜백을 부른다."""

    def __init__(self, request: RunRequest, on_permission: PermissionCallback, script: list[Any]) -> None:
        self.request = request
        self.on_permission = on_permission
        self.script = script
        self.interrupted = False

    async def events(self) -> AsyncIterator[RuntimeEvent]:
        yield RuntimeEvent("session.started", {"session_id": "sess-1"})
        for step in self.script:
            if self.interrupted:
                break
            if step[0] == "text":
                for piece in step[1].split(" "):
                    yield RuntimeEvent("message.delta", {"text": piece + " "})
                yield RuntimeEvent("message", {"text": step[1]})
            elif step[0] == "tool":
                _, tool, tool_input = step
                decision = await self.on_permission(tool, tool_input)
                yield RuntimeEvent("tool.started", {"id": tool, "tool": tool, "input": tool_input})
                yield RuntimeEvent("tool.completed" if decision.allow else "tool.failed", {"id": tool})
            elif step[0] == "sleep":
                await asyncio.sleep(step[1])
        yield RuntimeEvent(
            "turn.completed",
            {
                "session_id": "sess-1",
                "is_error": False,
                "cost_usd": 0.01,
                "duration_ms": 5,
                "interrupted": self.interrupted,
            },
        )

    async def interrupt(self) -> None:
        self.interrupted = True


class FakeRuntime:
    id = "claude-code"
    name = "Fake"

    def __init__(self) -> None:
        self.script: list[Any] = [("text", "안녕하세요 반갑습니다")]
        self.requests: list[RunRequest] = []

    def detect(self) -> Any:  # pragma: no cover
        raise NotImplementedError

    def start(self, request: RunRequest, on_permission: PermissionCallback) -> FakeRun:
        self.requests.append(request)
        return FakeRun(request, on_permission, self.script)


@pytest.fixture
def fake() -> FakeRuntime:
    return FakeRuntime()


@pytest.fixture
def chat(settings: Settings, fake: FakeRuntime) -> Iterator[TestClient]:
    with TestClient(
        create_app(settings, runtime_for=lambda _id: fake), base_url="http://127.0.0.1:8000"
    ) as c:
        yield c


def wait_message(client: TestClient, conv_id: str, message_id: str, timeout: float = 5) -> dict[str, Any]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        conv = client.get(f"/api/v1/conversations/{conv_id}").json()
        msg = next(m for m in conv["messages"] if m["id"] == message_id)
        if msg["status"] not in ("pending", "streaming"):
            return msg
        time.sleep(0.05)
    raise AssertionError("message did not finish")


def setup_org(client: TestClient) -> tuple[dict[str, Any], dict[str, Any]]:
    org = client.post("/api/v1/organizations/from-template", json={"template_key": "software"}).json()
    conv = client.post("/api/v1/conversations", json={"organization_id": org["id"]}).json()
    return org, conv


def test_org_chat_routes_to_ceo_streams_and_persists(chat: TestClient, fake: FakeRuntime) -> None:
    org, conv = setup_org(chat)
    with chat.websocket_connect("ws://127.0.0.1:8000/api/v1/ws") as ws:
        res = chat.post(f"/api/v1/conversations/{conv['id']}/messages", json={"content": "시장 조사 해 줘"})
        assert res.status_code == 202
        reply_id = res.json()["assistant_message_ids"][0]
        types = []
        while "message.completed" not in types:
            types.append(ws.receive_json()["type"])
    assert "message.delta" in types and "agent.status" in types
    msg = wait_message(chat, conv["id"], reply_id)
    assert msg["status"] == "done" and msg["content"] == "안녕하세요 반갑습니다"
    ceo = next(a for a in org["agents"] if a["is_lead"])
    assert msg["agent_id"] == ceo["id"]
    req = fake.requests[0]
    assert "조직 구성:" in req.system_prompt_append and "QA 엔지니어" in req.system_prompt_append
    assert "Bash" in req.disallowed_tools  # 기본 권한: 셸 금지
    assert chat.get(f"/api/v1/conversations/{conv['id']}").json()["title"] == "시장 조사 해 줘"
    assert chat.get(f"/api/v1/agents/{ceo['id']}").json()["status"] == "completed"

    # 다음 턴은 같은 Claude Code 세션을 이어 간다.
    res = chat.post(f"/api/v1/conversations/{conv['id']}/messages", json={"content": "계속"})
    wait_message(chat, conv["id"], res.json()["assistant_message_ids"][0])
    assert fake.requests[1].resume_session_id == "sess-1"


def test_mentions_route_to_agents_and_all(chat: TestClient, fake: FakeRuntime) -> None:
    org, conv = setup_org(chat)
    dev = next(a for a in org["agents"] if a["name"] == "백엔드 개발자")
    res = chat.post(
        f"/api/v1/conversations/{conv['id']}/messages",
        json={"content": "API 설계해 줘", "mention_agent_ids": [dev["id"]]},
    )
    msg = wait_message(chat, conv["id"], res.json()["assistant_message_ids"][0])
    assert msg["agent_id"] == dev["id"]
    assert "조직 구성:" not in fake.requests[-1].system_prompt_append
    res = chat.post(
        f"/api/v1/conversations/{conv['id']}/messages", json={"content": "공지", "mention_all": True}
    )
    wait_message(chat, conv["id"], res.json()["assistant_message_ids"][0])
    assert "[조직 전체 공지]" in fake.requests[-1].prompt
    other = chat.post("/api/v1/organizations", json={"name": "Other"}).json()
    res = chat.post(
        f"/api/v1/conversations/{conv['id']}/messages",
        json={"content": "x", "mention_agent_ids": [other["agents"][0]["id"]]},
    )
    assert res.status_code == 422


def test_team_chat_routes_to_department_head(chat: TestClient, fake: FakeRuntime) -> None:
    org, _ = setup_org(chat)
    dept = next(d for d in org["departments"] if d["name"] == "개발팀")
    conv = chat.post(
        "/api/v1/conversations",
        json={"organization_id": org["id"], "target_kind": "team", "target_id": dept["id"]},
    ).json()
    res = chat.post(f"/api/v1/conversations/{conv['id']}/messages", json={"content": "진행 상황?"})
    msg = wait_message(chat, conv["id"], res.json()["assistant_message_ids"][0])
    head = next(a for a in org["agents"] if a["name"] == "프론트엔드 개발자")
    assert msg["agent_id"] == head["id"]
    assert "팀 대화: 개발팀" in fake.requests[-1].system_prompt_append


def test_approval_flow_allow_and_deny(chat: TestClient, fake: FakeRuntime) -> None:
    org, conv = setup_org(chat)
    ceo = next(a for a in org["agents"] if a["is_lead"])
    perms = {**ceo["permissions"], "allow_shell": True, "require_approval": ["shell"]}
    chat.patch(f"/api/v1/organizations/{org['id']}/agents/{ceo['id']}", json={"permissions": perms})
    fake.script = [("tool", "Bash", {"command": "npm test"}), ("text", "끝")]
    with chat.websocket_connect("ws://127.0.0.1:8000/api/v1/ws") as ws:
        res = chat.post(f"/api/v1/conversations/{conv['id']}/messages", json={"content": "테스트 돌려"})
        reply_id = res.json()["assistant_message_ids"][0]
        while True:
            event = ws.receive_json()
            if event["type"] == "approval.requested":
                break
    approval = event["approval"]
    assert approval["tool"] == "Bash" and approval["target"] == "npm test"
    assert chat.get(f"/api/v1/agents/{ceo['id']}").json()["status"] == "waiting"
    pending = chat.get("/api/v1/approvals", params={"organization_id": org["id"]}).json()
    assert [p["id"] for p in pending] == [approval["id"]]
    assert chat.post(f"/api/v1/approvals/{approval['id']}/decision", json={"allow": True}).status_code == 200
    msg = wait_message(chat, conv["id"], reply_id)
    assert msg["activity"][0]["activity"] == "testing" and msg["activity"][0]["status"] == "done"
    assert chat.post(f"/api/v1/approvals/{approval['id']}/decision", json={"allow": True}).status_code == 409

    # 셸이 금지된 에이전트의 명령은 묻지 않고 거부된다.
    chat.patch(
        f"/api/v1/organizations/{org['id']}/agents/{ceo['id']}",
        json={"permissions": {**perms, "allow_shell": False}},
    )
    res = chat.post(f"/api/v1/conversations/{conv['id']}/messages", json={"content": "또"})
    msg = wait_message(chat, conv["id"], res.json()["assistant_message_ids"][0])
    assert msg["activity"][0]["status"] == "failed"
    assert chat.get("/api/v1/approvals", params={"organization_id": org["id"]}).json() == []


def test_path_outside_scope_denied_without_asking(chat: TestClient, fake: FakeRuntime) -> None:
    _, conv = setup_org(chat)
    fake.script = [("tool", "Write", {"file_path": "/etc/passwd", "content": "x"})]
    res = chat.post(f"/api/v1/conversations/{conv['id']}/messages", json={"content": "x"})
    msg = wait_message(chat, conv["id"], res.json()["assistant_message_ids"][0])
    assert msg["activity"][0]["status"] == "failed"


def test_stop_interrupts_run(chat: TestClient, fake: FakeRuntime) -> None:
    _, conv = setup_org(chat)
    fake.script = [("sleep", 0.3), ("text", "너무 늦음"), ("sleep", 5)]
    res = chat.post(f"/api/v1/conversations/{conv['id']}/messages", json={"content": "오래 걸리는 일"})
    reply_id = res.json()["assistant_message_ids"][0]
    time.sleep(0.1)
    assert (
        chat.post(f"/api/v1/conversations/{conv['id']}/messages", json={"content": "또"}).status_code == 409
    )
    assert chat.post(f"/api/v1/conversations/{conv['id']}/stop").json()["stopped"] == 1
    msg = wait_message(chat, conv["id"], reply_id, timeout=8)
    assert msg["status"] == "interrupted"


def test_commands(chat: TestClient, fake: FakeRuntime) -> None:
    org, conv = setup_org(chat)
    names = [c["name"] for c in chat.get("/api/v1/commands").json()]
    assert names == [
        "help",
        "agents",
        "delegate",
        "team",
        "project",
        "tasks",
        "status",
        "stop",
        "approve",
        "skills",
        "mcp",
        "clear",
    ]

    def run(name: str, **args: str) -> dict[str, Any]:
        url = f"/api/v1/conversations/{conv['id']}/commands"
        return chat.post(url, json={"name": name, "args": args}).json()

    assert len(run("agents")["data"]["result"]["rows"]) == 8
    assert run("delegate")["status"] == "error"
    res = run("delegate", agent="@QA 엔지니어", task="경쟁사 3곳 조사")
    assert res["status"] == "done"
    tasks = chat.get("/api/v1/tasks", params={"organization_id": org["id"]}).json()
    assert tasks[0]["title"] == "경쟁사 3곳 조사"
    deadline = time.time() + 5
    while chat.get("/api/v1/tasks", params={"organization_id": org["id"]}).json()[0]["status"] == "running":
        assert time.time() < deadline
        time.sleep(0.05)
    assert chat.get("/api/v1/tasks", params={"organization_id": org["id"]}).json()[0]["status"] == "done"
    assert run("team", department="개발팀")["data"]["result"]["action"]["type"] == "conversation.updated"
    assert chat.get(f"/api/v1/conversations/{conv['id']}").json()["target_kind"] == "team"
    cleared = run("clear")["data"]["result"]["action"]
    assert chat.get(f"/api/v1/conversations/{cleared['id']}").status_code == 200
    assert run("nope")["status"] == "error"


def test_attachments_validated_and_delivered(chat: TestClient, fake: FakeRuntime, settings: Settings) -> None:
    _, conv = setup_org(chat)
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
    up = chat.post("/api/v1/attachments", files={"file": ("../../shot.png", png, "image/png")})
    assert up.status_code == 201
    a = up.json()
    assert a["filename"] == "shot.png" and a["media_type"] == "image/png"
    bad = chat.post("/api/v1/attachments", files={"file": ("fake.png", b"not a png", "image/png")})
    assert bad.status_code == 415
    exe = chat.post("/api/v1/attachments", files={"file": ("run.exe", b"MZ", "application/octet-stream")})
    assert exe.status_code == 415
    res = chat.post(
        f"/api/v1/conversations/{conv['id']}/messages",
        json={"content": "이 그림 봐", "attachment_ids": [a["id"]]},
    )
    wait_message(chat, conv["id"], res.json()["assistant_message_ids"][0])
    req = fake.requests[-1]
    stored = Path(req.add_dirs[0])
    assert stored.parent == settings.upload_root
    assert str(stored / "shot.png") in req.prompt
    assert chat.get(f"/api/v1/attachments/{a['id']}/content").content == png
    assert chat.delete(f"/api/v1/attachments/{a['id']}").status_code == 409
    # 같은 첨부를 다른 대화에 다시 쓸 수 없다.
    res = chat.post(
        f"/api/v1/conversations/{conv['id']}/messages", json={"content": "또", "attachment_ids": [a["id"]]}
    )
    assert res.status_code == 404
    assert chat.delete(f"/api/v1/conversations/{conv['id']}").status_code == 204
    assert not stored.exists()


def test_context_validation(chat: TestClient, tmp_path: Path) -> None:
    _, conv = setup_org(chat)
    url = f"/api/v1/conversations/{conv['id']}"
    assert chat.patch(url, json={"context": [{"kind": "path", "ref": "src"}]}).status_code == 422
    root = tmp_path / "code"
    (root / "app" / "src").mkdir(parents=True)
    (root / "app" / "package.json").write_text("{}")
    chat.post("/api/v1/project-roots", json={"path": str(root)})
    project = chat.post("/api/v1/projects", json={"path": str(root / "app")}).json()
    chat.patch(url, json={"project_id": project["id"]})
    assert chat.patch(url, json={"context": [{"kind": "path", "ref": "src"}]}).status_code == 200
    assert chat.patch(url, json={"context": [{"kind": "path", "ref": "../../.."}]}).status_code == 422
    assert chat.patch(url, json={"context": [{"kind": "github", "ref": "a/b; rm -rf"}]}).status_code == 422
    assert (
        chat.patch(url, json={"context": [{"kind": "github", "ref": "apg0001/Agent-Office"}]}).status_code
        == 200
    )
    tree = chat.get(f"/api/v1/projects/{project['id']}/tree").json()
    assert [e["name"] for e in tree["entries"]] == ["src", "package.json"]
    assert chat.get(f"/api/v1/projects/{project['id']}/tree", params={"path": "../.."}).status_code == 403
