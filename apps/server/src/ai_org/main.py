"""FastAPI 앱 진입점."""

from __future__ import annotations

import asyncio
import contextlib
import mimetypes
import os
import signal
import sys
import threading
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import Response
from starlette.types import Scope

from ai_org import __version__
from ai_org.api import auth as auth_api
from ai_org.api import chat, designs, desktop, organizations, projects, system, usage
from ai_org.config import Settings
from ai_org.db import init_db, make_engine, session_factory
from ai_org.models import Attachment
from ai_org.runtime.base import AgentRuntime
from ai_org.runtime.claude_code import ClaudeCodeRuntime
from ai_org.security import AuthMiddleware, LocalOnlyMiddleware
from ai_org.services import attachments as att
from ai_org.services.auth import LoginThrottle
from ai_org.services.bus import EventBus
from ai_org.services.notify import Notifier
from ai_org.services.runs import RunManager
from ai_org.services.usage import UsageMonitor

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
        app.state.usage = UsageMonitor()
        app.state.notifier = Notifier(runs.bus, factory)
        notifier_task = asyncio.create_task(app.state.notifier.run())
        poller = (
            asyncio.create_task(usage.poll(app, settings.usage_poll_s)) if settings.usage_poll_s > 0 else None
        )
        yield
        if poller is not None:
            poller.cancel()
        notifier_task.cancel()
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
    app.add_middleware(AuthMiddleware, enabled=settings.auth_enabled, desktop_token=settings.desktop_token)
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
    app.include_router(usage.router)
    app.include_router(desktop.router)
    if settings.web_dist is not None and (settings.web_dist / "index.html").is_file():
        # 단일 프로세스: 백엔드가 웹 화면도 제공한다(데스크톱 번들, AI_ORG_WEB_DIST).
        # /api는 위 라우터가 먼저 받는다.
        app.mount("/", SpaFiles(directory=settings.web_dist, html=True), name="web")
    return app


# PWA 매니페스트(#73). 표준 mimetypes에 없어 등록한다.
mimetypes.add_type("application/manifest+json", ".webmanifest")


class SpaFiles(StaticFiles):
    """정적 파일 + SPA 대체: 없는 경로(/usage 등 화면 주소)는 index.html. /api 아래는 대체하지 않는다."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        try:
            response = await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code != 404 or path == "api" or path.startswith("api/"):
                raise
            response = await super().get_response("index.html", scope)
            path = "index.html"
        if path in ("sw.js", "index.html", "", "."):
            # 서비스 워커와 화면 HTML은 늘 새로 확인한다(새 릴리스가 바로 반영되게).
            response.headers["Cache-Control"] = "no-cache"
        return response


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
    if os.environ.get("AI_ORG_EXIT_ON_STDIN_EOF") == "1":
        _exit_when_parent_closes_stdin()
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port)


def _exit_when_parent_closes_stdin() -> None:
    """데스크톱 앱이 끝나면(표준 입력이 닫히면) 정상 종료 신호를 보낸다.

    앱이 강제 종료돼도 파이프는 운영체제가 닫으므로 백엔드가 고아 프로세스로 남지 않는다.
    """

    def watch() -> None:
        # 버퍼 없는 os.read: 종료 시 버퍼 잠금 충돌(Fatal Python error) 없이 데몬 스레드가 끝난다.
        with contextlib.suppress(OSError, ValueError):
            fd = sys.stdin.fileno()
            while os.read(fd, 4096):
                pass
        if sys.platform == "win32":
            # Windows의 os.kill(SIGTERM)은 즉시 강제 종료다. SIGINT를 올려 uvicorn이 정상 종료하게 한다.
            signal.raise_signal(signal.SIGINT)
        else:
            os.kill(os.getpid(), signal.SIGTERM)

    threading.Thread(target=watch, name="stdin-eof", daemon=True).start()


app = create_app()
