"""FastAPI 앱 진입점."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

from fastapi import FastAPI
from sqlalchemy import select

from ai_org import __version__
from ai_org.api import auth as auth_api
from ai_org.api import chat, designs, organizations, projects, system
from ai_org.config import Settings
from ai_org.db import init_db, make_engine, session_factory
from ai_org.models import Attachment
from ai_org.runtime.base import AgentRuntime
from ai_org.runtime.claude_code import ClaudeCodeRuntime
from ai_org.security import AuthMiddleware, LocalOnlyMiddleware
from ai_org.services import attachments as att
from ai_org.services.auth import LoginThrottle
from ai_org.services.bus import EventBus
from ai_org.services.runs import RunManager

DRAFT_ATTACHMENT_TTL = timedelta(hours=24)


def create_app(
    settings: Settings | None = None, runtime_for: Callable[[str], AgentRuntime] | None = None
) -> FastAPI:
    settings = settings or Settings()

    def default_runtime(runtime_id: str) -> AgentRuntime:
        if runtime_id != "claude-code":
            raise ValueError(f"unsupported runtime: {runtime_id}")
        if settings.runtime_override == "fake":
            from ai_org.runtime.fake import FakeRuntime

            return FakeRuntime()
        return ClaudeCodeRuntime(settings.claude_bin)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        settings.home.mkdir(parents=True, exist_ok=True, mode=0o700)
        settings.upload_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        engine = make_engine(settings.database_url)
        init_db(engine)
        factory = session_factory(engine)
        app.state.engine = engine
        app.state.session_factory = factory
        runs = RunManager(settings, factory, EventBus(), runtime_for or default_runtime)
        runs.recover()
        _purge_draft_attachments(factory, settings)
        app.state.runs = runs
        app.state.design_tasks = set()
        yield
        for task in list(app.state.design_tasks):
            task.cancel()
        await runs.shutdown()
        engine.dispose()

    app = FastAPI(
        title="AI Organization Platform",
        version=__version__,
        lifespan=lifespan,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        redoc_url=None,
    )
    app.state.settings = settings
    app.state.login_throttle = LoginThrottle()
    # 미들웨어는 나중에 추가한 것이 바깥이다: Host·Origin 검사(LocalOnly) → 로그인 검사(Auth) 순서로 거친다.
    app.add_middleware(AuthMiddleware, enabled=settings.auth_enabled)
    app.add_middleware(
        LocalOnlyMiddleware,
        allowed_hosts=settings.allowed_hosts,
        allowed_origins=settings.allowed_origins,
        multipart_paths={"/api/v1/attachments"},
    )
    app.include_router(auth_api.router)
    app.include_router(system.router)
    app.include_router(organizations.router)
    app.include_router(projects.router)
    app.include_router(chat.router)
    app.include_router(designs.router)
    return app


def _purge_draft_attachments(factory, settings: Settings) -> None:  # type: ignore[no-untyped-def]
    cutoff = datetime.now(UTC) - DRAFT_ATTACHMENT_TTL
    with factory() as db:
        for a in db.scalars(select(Attachment).where(Attachment.conversation_id.is_(None))):
            if a.created_at < cutoff:
                att.remove(a.stored_path, settings.upload_root)
                db.delete(a)
        db.commit()


def run() -> None:
    import uvicorn

    settings = Settings()
    if settings.host not in {"127.0.0.1", "localhost", "::1"}:
        raise SystemExit("AI_ORG_HOST must be a loopback address; remote exposure is not supported.")
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port)


app = create_app()
