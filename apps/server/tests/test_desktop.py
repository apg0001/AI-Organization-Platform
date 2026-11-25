"""데스크톱 요약 API·알림 센터·단일 프로세스 웹 제공."""

from __future__ import annotations

import dataclasses
import time
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from ai_org.config import Settings
from ai_org.main import create_app
from tests.test_chat import FakeRuntime, setup_org, wait_message


def _desktop(settings: Settings, fake: FakeRuntime | None = None, **changes: Any) -> TestClient:
    s = dataclasses.replace(settings, desktop_token="tok-123", **changes)
    runtime = (lambda _id: fake) if fake else None
    return TestClient(create_app(s, runtime_for=runtime), base_url="http://127.0.0.1:8000")


def test_desktop_api_requires_configured_token(client: TestClient, settings: Settings) -> None:
    assert client.get("/api/v1/desktop/summary").status_code == 404  # 브라우저 실행: 경로 없음
    with _desktop(settings) as c:
        assert c.get("/api/v1/desktop/summary").status_code == 401
        assert c.get("/api/v1/desktop/summary", headers={"Authorization": "Bearer nope"}).status_code == 401
        res = c.get("/api/v1/desktop/summary", headers={"Authorization": "Bearer tok-123"})
        assert res.status_code == 200
        assert res.json() | {"version": None} == {
            "version": None,
            "running": 0,
            "approvals": 0,
            "usage": [],
            "notifications": [],
            "latest_id": 0,
        }


def test_desktop_token_works_with_login_enabled(settings: Settings) -> None:
    with _desktop(settings, auth_enabled=True) as c:
        assert c.get("/api/v1/organizations").status_code == 401  # 다른 API는 여전히 로그인 필요
        res = c.get("/api/v1/desktop/summary", headers={"Authorization": "Bearer tok-123"})
        assert res.status_code == 200


def _summary(c: TestClient, after: int = 0) -> dict[str, Any]:
    return c.get(f"/api/v1/desktop/summary?after={after}", headers={"Authorization": "Bearer tok-123"}).json()


def _wait_notes(c: TestClient, count: int, after: int = 0) -> list[dict[str, Any]]:
    deadline = time.time() + 5
    while time.time() < deadline:
        notes: list[dict[str, Any]] = _summary(c, after)["notifications"]
        if len(notes) >= count:
            return notes
        time.sleep(0.05)
    raise AssertionError("notification did not arrive")


def test_notifications_for_approval_completion_and_usage(settings: Settings) -> None:
    fake = FakeRuntime()
    with _desktop(settings, fake) as c:
        org, conv = setup_org(c)
        ceo = next(a for a in org["agents"] if a["is_lead"])
        perms = {**ceo["permissions"], "allow_shell": True, "require_approval": ["shell"]}
        c.patch(f"/api/v1/organizations/{org['id']}/agents/{ceo['id']}", json={"permissions": perms})
        fake.script = [("tool", "Bash", {"command": "npm test"}), ("text", "테스트 통과")]
        res = c.post(f"/api/v1/conversations/{conv['id']}/messages", json={"content": "테스트 돌려"})
        reply_id = res.json()["assistant_message_ids"][0]

        approval_note = _wait_notes(c, 1)[0]
        assert approval_note["kind"] == "approval" and approval_note["title"] == "승인 요청"
        assert approval_note["body"] == f"{ceo['name']}: Bash npm test"
        assert approval_note["url"] == f"/command/{conv['id']}"
        assert _summary(c)["approvals"] == 1
        approval_id = c.get(f"/api/v1/approvals?organization_id={org['id']}").json()[0]["id"]
        assert c.post(f"/api/v1/approvals/{approval_id}/decision", json={"allow": True}).status_code == 200
        wait_message(c, conv["id"], reply_id)

        done = _wait_notes(c, 1, after=approval_note["id"])[0]
        assert done["kind"] == "done" and done["body"] == f"{ceo['name']}: 테스트 통과"
        # 커서 이후만 돌려준다.
        assert _summary(c, after=done["id"])["notifications"] == []

        # 사용량 임계치 이벤트도 알림이 된다(버스로 들어온 사실 이벤트를 그대로 변환).
        c.app.state.runs.bus.publish("usage.threshold", summary="Claude 주간 사용량 91% — 90% 도달")  # type: ignore[attr-defined]
        usage_note = _wait_notes(c, 1, after=done["id"])[0]
        assert usage_note["kind"] == "usage" and usage_note["url"] == "/usage"


def test_delegated_sub_runs_do_not_notify(settings: Settings) -> None:
    fake = FakeRuntime()
    with _desktop(settings, fake) as c:
        notifier = c.app.state.notifier  # type: ignore[attr-defined]
        sub = {"role": "assistant", "status": "done", "data": {"delegated_by": "x"}, "content": "보고"}
        assert notifier.convert({"type": "message.completed", "message": sub}) is None
        stopped = {"role": "assistant", "status": "interrupted", "data": {}}
        assert notifier.convert({"type": "message.completed", "message": stopped}) is None
        assert notifier.convert({"type": "agent.status"}) is None


def test_serves_web_build_with_spa_fallback(settings: Settings, tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>app</html>")
    (dist / "assets" / "app.js").write_text("console.log(1)")
    (dist / "sw.js").write_text("self.addEventListener('fetch', () => {})")
    (dist / "manifest.webmanifest").write_text('{"name": "AI Organization"}')
    s = dataclasses.replace(settings, web_dist=dist)
    with TestClient(create_app(s), base_url="http://127.0.0.1:8000") as c:
        assert c.get("/").text == "<html>app</html>"
        assert c.get("/assets/app.js").text == "console.log(1)"
        assert c.get("/usage").text == "<html>app</html>"  # 화면 주소는 index.html
        # PWA(#73): 매니페스트 형식, 서비스 워커·화면 HTML은 늘 새로 확인, 해시 파일은 캐시 허용.
        assert c.get("/manifest.webmanifest").headers["content-type"].startswith("application/manifest+json")
        assert c.get("/sw.js").headers["cache-control"] == "no-cache"
        assert c.get("/").headers["cache-control"] == "no-cache"
        assert c.get("/usage").headers["cache-control"] == "no-cache"
        assert "cache-control" not in c.get("/assets/app.js").headers
        assert c.get("/api/v1/system/health").json() == {"status": "ok"}
        assert c.get("/api/v1/nope").status_code == 404  # API는 대체하지 않는다
        assert c.get("/", headers={"Host": "evil.example"}).status_code == 403  # Host 검사 그대로
