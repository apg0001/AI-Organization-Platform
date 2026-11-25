"""로그인·계정 API.

로컬 단일 사용자 모드: 첫 계정 생성 뒤에는 새 계정을 만들 수 없다(다중 사용자는 SECURITY.md 후속).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from ai_org.deps import DB, AppSettings
from ai_org.models import User
from ai_org.services import auth

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
USERNAME = r"^[A-Za-z0-9_.\-]{3,40}$"


class SetupIn(BaseModel):
    username: str = Field(pattern=USERNAME)
    password: str = Field(min_length=auth.MIN_PASSWORD, max_length=200)
    display_name: str = Field(default="", max_length=80)


class LoginIn(BaseModel):
    username: str = Field(max_length=40)
    password: str = Field(max_length=200)


class MeIn(BaseModel):
    display_name: str | None = Field(default=None, max_length=80)
    settings: dict[str, Any] | None = None


class PasswordIn(BaseModel):
    current_password: str = Field(max_length=200)
    new_password: str = Field(min_length=auth.MIN_PASSWORD, max_length=200)


def _user_json(user: User) -> dict[str, Any]:
    return {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name or user.username,
        "settings": user.settings or {},
    }


def _set_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        auth.COOKIE,
        token,
        max_age=int(auth.SESSION_TTL.total_seconds()),
        httponly=True,
        samesite="strict",
        path="/",
    )


def current_user(request: Request, db: DB) -> User | None:
    return auth.user_for_token(db, request.cookies.get(auth.COOKIE))


def require_user(request: Request, db: DB) -> User:
    user = current_user(request, db)
    if user is None:
        raise HTTPException(401, "로그인이 필요합니다.")
    return user


@router.get("/status")
def status(request: Request, db: DB, settings: AppSettings) -> dict[str, Any]:
    if not settings.auth_enabled:
        return {"auth_enabled": False, "setup_required": False, "authenticated": True, "user": None}
    user = current_user(request, db)
    return {
        "auth_enabled": True,
        "setup_required": not auth.has_users(db),
        "authenticated": user is not None,
        "user": _user_json(user) if user else None,
    }


@router.post("/setup", status_code=201)
def setup(body: SetupIn, response: Response, db: DB, settings: AppSettings) -> dict[str, Any]:
    if not settings.auth_enabled:
        raise HTTPException(409, "로그인이 꺼져 있습니다(AI_ORG_AUTH=off).")
    if auth.has_users(db):
        raise HTTPException(409, "이미 계정이 있습니다. 로그인하세요.")
    user = User(
        username=body.username,
        display_name=body.display_name,
        password_hash=auth.hash_password(body.password),
    )
    db.add(user)
    db.commit()
    _set_cookie(response, auth.create_session(db, user))
    return _user_json(user)


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response, db: DB) -> dict[str, Any]:
    throttle: auth.LoginThrottle = request.app.state.login_throttle
    key = body.username.lower()
    wait = throttle.wait_seconds(key)
    if wait > 0:
        raise HTTPException(429, f"로그인 시도가 너무 많습니다. {int(wait) + 1}초 뒤에 다시 시도하세요.")
    from sqlalchemy import select

    user = db.scalar(select(User).where(User.username == body.username))
    # 아이디가 없어도 같은 비용으로 검증해 존재 여부가 시간으로 드러나지 않게 한다.
    ok = auth.verify_password(body.password, user.password_hash if user else auth.DUMMY_HASH)
    if user is None or not ok:
        throttle.failed(key)
        raise HTTPException(401, "아이디 또는 비밀번호가 올바르지 않습니다.")
    throttle.succeeded(key)
    _set_cookie(response, auth.create_session(db, user))
    return _user_json(user)


@router.post("/logout", status_code=204)
def logout(request: Request, db: DB) -> Response:
    auth.end_session(db, request.cookies.get(auth.COOKIE))
    response = Response(status_code=204)
    response.delete_cookie(auth.COOKIE, path="/")
    return response


@router.patch("/me")
def update_me(body: MeIn, request: Request, db: DB) -> dict[str, Any]:
    user = require_user(request, db)
    if body.display_name is not None:
        user.display_name = body.display_name
    if body.settings is not None:
        user.settings = body.settings
    db.commit()
    return _user_json(user)


@router.post("/password", status_code=204)
def change_password(body: PasswordIn, request: Request, db: DB) -> Response:
    user = require_user(request, db)
    if not auth.verify_password(body.current_password, user.password_hash):
        raise HTTPException(403, "현재 비밀번호가 올바르지 않습니다.")
    user.password_hash = auth.hash_password(body.new_password)
    db.commit()
    # 다른 기기·브라우저의 세션은 끊는다.
    auth.end_other_sessions(db, user.id, request.cookies.get(auth.COOKIE))
    return Response(status_code=204)
