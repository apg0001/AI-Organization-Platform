from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from starlette.websockets import WebSocketDisconnect

from ai_org.config import Settings
from ai_org.main import create_app
from ai_org.models import AuthSession, User
from ai_org.services import auth

BASE = "http://127.0.0.1:8000"


@pytest.fixture
def api(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(replace(settings, auth_enabled=True)), base_url=BASE) as c:
        yield c


def setup_account(api: TestClient) -> None:
    res = api.post(
        "/api/v1/auth/setup", json={"username": "owner", "password": "correct horse", "display_name": "주인"}
    )
    assert res.status_code == 201


def test_setup_login_logout_flow(api: TestClient) -> None:
    assert api.get("/api/v1/auth/status").json() == {
        "auth_enabled": True,
        "setup_required": True,
        "authenticated": False,
        "user": None,
    }
    assert api.get("/api/v1/organizations").status_code == 401
    assert api.get("/api/docs").status_code == 401
    assert api.get("/api/v1/system/health").status_code == 200
    assert api.post("/api/v1/auth/setup", json={"username": "owner", "password": "short"}).status_code == 422
    setup_account(api)
    # 계정 생성 후 자동 로그인(쿠키), 두 번째 계정은 만들 수 없다.
    assert api.get("/api/v1/organizations").status_code == 200
    assert (
        api.post("/api/v1/auth/setup", json={"username": "other", "password": "password123"}).status_code
        == 409
    )
    cookie = api.cookies.get(auth.COOKIE)
    assert cookie and len(cookie) > 30
    api.post("/api/v1/auth/logout")
    assert api.get("/api/v1/organizations").status_code == 401
    assert (
        api.post("/api/v1/auth/login", json={"username": "owner", "password": "wrong pass"}).status_code
        == 401
    )
    res = api.post("/api/v1/auth/login", json={"username": "owner", "password": "correct horse"})
    assert res.status_code == 200 and res.json()["display_name"] == "주인"
    assert api.get("/api/v1/auth/status").json()["authenticated"] is True


def test_secrets_not_stored_in_plaintext(api: TestClient) -> None:
    setup_account(api)
    token = api.cookies.get(auth.COOKIE)
    with api.app.state.session_factory() as db:  # type: ignore[attr-defined]
        user = db.scalar(select(User))
        session = db.scalar(select(AuthSession))
    assert user is not None and session is not None
    assert "correct horse" not in user.password_hash and user.password_hash.startswith("scrypt$")
    assert session.token_hash != token and len(session.token_hash) == 64


def test_websocket_requires_login(api: TestClient) -> None:
    with pytest.raises(WebSocketDisconnect) as exc, api.websocket_connect("ws://127.0.0.1:8000/api/v1/ws"):
        pass
    assert exc.value.code == 4401
    setup_account(api)
    with api.websocket_connect("ws://127.0.0.1:8000/api/v1/ws") as ws:
        api.post("/api/v1/organizations", json={"name": "x"})
        ws.close()


def test_login_throttle(api: TestClient) -> None:
    setup_account(api)
    api.post("/api/v1/auth/logout")
    codes = [
        api.post("/api/v1/auth/login", json={"username": "owner", "password": "nope-nope"}).status_code
        for _ in range(6)
    ]
    assert codes[:5] == [401] * 5 and codes[5] == 429
    # 대기 중에는 맞는 비밀번호도 거절된다.
    assert (
        api.post("/api/v1/auth/login", json={"username": "owner", "password": "correct horse"}).status_code
        == 429
    )


def test_password_change_revokes_other_sessions(settings: Settings) -> None:
    app = create_app(replace(settings, auth_enabled=True))
    with TestClient(app, base_url=BASE) as a, TestClient(app, base_url=BASE) as b:
        setup_account(a)
        assert (
            b.post("/api/v1/auth/login", json={"username": "owner", "password": "correct horse"}).status_code
            == 200
        )
        assert (
            a.post(
                "/api/v1/auth/password", json={"current_password": "bad", "new_password": "new password"}
            ).status_code
            == 403
        )
        res = a.post(
            "/api/v1/auth/password",
            json={"current_password": "correct horse", "new_password": "new password"},
        )
        assert res.status_code == 204
        assert a.get("/api/v1/organizations").status_code == 200  # 바꾼 쪽은 유지
        assert b.get("/api/v1/organizations").status_code == 401  # 다른 세션은 끊김
        assert a.patch(
            "/api/v1/auth/me", json={"display_name": "새 이름", "settings": {"theme": "dark"}}
        ).json()["settings"] == {"theme": "dark"}


def test_auth_off_mode(client: TestClient) -> None:
    assert client.get("/api/v1/auth/status").json()["auth_enabled"] is False
    assert client.get("/api/v1/organizations").status_code == 200
