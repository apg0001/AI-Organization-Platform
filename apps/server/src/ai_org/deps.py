"""FastAPI 의존성. 앱 상태(app.state)에 엔진·설정을 두고 요청마다 세션을 연다."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ai_org.config import Settings


def get_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_db(request: Request) -> Iterator[Session]:
    with request.app.state.session_factory() as session:
        yield session


DB = Annotated[Session, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_settings)]


def not_found(what: str) -> HTTPException:
    return HTTPException(status_code=404, detail=f"{what} not found")
