"""로컬 서버 보호.

이 서버는 사용자의 파일 시스템과 Claude Code를 다룬다. 루프백에만 바인딩하더라도 브라우저에서 열린
임의의 웹사이트가 localhost로 요청을 보내거나(CSRF), DNS 리바인딩으로 Host를 바꿔 접근할 수 있다.
따라서 다음을 강제한다.

1. Host 헤더 허용 목록(localhost, 127.0.0.1, [::1]) — DNS 리바인딩 차단.
2. Origin 헤더가 있으면 허용 목록과 일치해야 함 — 다른 사이트의 요청 차단.
3. 상태 변경 요청(POST/PUT/PATCH/DELETE)은 JSON만 받음 — 단순 폼 CSRF 차단.
   예외: 업로드 경로의 multipart. 교차 출처 폼 전송은 브라우저가 항상 Origin을 붙이므로 2번에서 막힌다.
   (같은 컴퓨터의 다른 프로세스는 막지 못한다 — 다중 사용자 인증은 docs/AUTH.md의 후속 단계.)
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def _host_name(host_header: str) -> str:
    if host_header.startswith("["):
        return host_header.split("]")[0] + "]"
    return host_header.rsplit(":", 1)[0] if ":" in host_header else host_header


class LocalOnlyMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app: ASGIApp,
        allowed_hosts: set[str],
        allowed_origins: set[str],
        multipart_paths: set[str] | None = None,
    ) -> None:
        super().__init__(app)
        self.allowed_hosts = allowed_hosts
        self.allowed_origins = allowed_origins
        # 파일 업로드 경로만 multipart를 받는다. 이 경로도 Origin 검사는 똑같이 적용된다.
        self.multipart_paths = multipart_paths or set()

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        host = _host_name(request.headers.get("host", ""))
        if host not in self.allowed_hosts:
            return JSONResponse({"detail": "host not allowed"}, status_code=403)

        origin = request.headers.get("origin")
        if origin is not None and origin not in self.allowed_origins:
            return JSONResponse({"detail": "origin not allowed"}, status_code=403)

        if request.method in UNSAFE_METHODS:
            content_type = request.headers.get("content-type", "")
            has_body = request.headers.get("content-length", "0") not in ("", "0")
            multipart_ok = request.url.path in self.multipart_paths and content_type.startswith(
                "multipart/form-data"
            )
            if has_body and not content_type.startswith("application/json") and not multipart_ok:
                return JSONResponse({"detail": "JSON body required"}, status_code=415)

        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        return response


AUTH_EXEMPT = {
    "/api/v1/system/health",
    "/api/v1/auth/status",
    "/api/v1/auth/setup",
    "/api/v1/auth/login",
    "/api/v1/auth/logout",
}


class AuthMiddleware(BaseHTTPMiddleware):
    """로그인 보호: /api 아래(문서 포함) 요청은 유효한 세션 쿠키가 있어야 한다.

    WebSocket은 엔드포인트(api/chat.py live)에서 같은 방식으로 검사한다.
    """

    def __init__(self, app: ASGIApp, enabled: bool) -> None:
        super().__init__(app)
        self.enabled = enabled

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        path = request.url.path
        if self.enabled and path.startswith("/api") and path not in AUTH_EXEMPT:
            from ai_org.services import auth

            with request.app.state.session_factory() as db:
                user = auth.user_for_token(db, request.cookies.get(auth.COOKIE))
            if user is None:
                return JSONResponse({"detail": "로그인이 필요합니다."}, status_code=401)
            request.state.user_id = user.id
        return await call_next(request)
