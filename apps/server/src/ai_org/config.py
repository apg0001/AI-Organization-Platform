"""런타임 설정. 환경 변수로만 바꾼다(설정 파일은 Phase 8에서 검토)."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path


def _default_web_dist() -> Path | None:
    """웹 빌드 폴더. 지정하면 백엔드가 화면까지 제공한다(단일 프로세스). 데스크톱 번들은 자동."""
    if value := os.environ.get("AI_ORG_WEB_DIST"):
        return Path(value).expanduser()
    bundle = getattr(sys, "_MEIPASS", None)  # PyInstaller 번들 안
    return Path(bundle) / "web" if bundle else None


def _default_home() -> Path:
    return Path(os.environ.get("AI_ORG_HOME", Path.home() / ".ai-org")).expanduser()


@dataclass(frozen=True)
class Settings:
    """서버 설정.

    - home: SQLite DB와 에이전트 작업 메타데이터를 두는 디렉터리.
    - host: 기본은 루프백. 외부 노출은 지원하지 않는다(docs/ARCHITECTURE.md 보안 절).
    - claude_home: Claude Code 사용자 설정 디렉터리(읽기 전용으로만 탐색).
    """

    home: Path = field(default_factory=_default_home)
    host: str = field(default_factory=lambda: os.environ.get("AI_ORG_HOST", "127.0.0.1"))
    port: int = field(default_factory=lambda: int(os.environ.get("AI_ORG_PORT", "8000")))
    web_port: int = field(default_factory=lambda: int(os.environ.get("AI_ORG_WEB_PORT", "3000")))
    claude_home: Path = field(
        default_factory=lambda: Path(
            os.environ.get("AI_ORG_CLAUDE_HOME", Path.home() / ".claude")
        ).expanduser()
    )
    # "fake"면 테스트용 가짜 런타임(E2E 전용, Claude를 실행하지 않음).
    runtime_override: str = field(default_factory=lambda: os.environ.get("AI_ORG_RUNTIME", ""))
    claude_bin: str = field(default_factory=lambda: os.environ.get("AI_ORG_CLAUDE_BIN", "claude"))
    # 동시에 실행하는 Claude Code 프로세스 수(라즈베리 파이 기준 보수적).
    # 로그인 보호(기본 켬). off면 루프백·Host·Origin 검사만으로 보호한다.
    auth_enabled: bool = field(default_factory=lambda: os.environ.get("AI_ORG_AUTH", "on").lower() != "off")
    # 사용량 자동 조회 주기(초). 0이면 끔(테스트).
    usage_poll_s: float = field(default_factory=lambda: float(os.environ.get("AI_ORG_USAGE_POLL", "60")))
    # 데스크톱 앱이 백엔드를 띄울 때 넘기는 임의 토큰. /api/v1/desktop/* 는 이 토큰으로만 열린다.
    desktop_token: str = field(default_factory=lambda: os.environ.get("AI_ORG_DESKTOP_TOKEN", ""))
    web_dist: Path | None = field(default_factory=_default_web_dist)
    max_concurrent_runs: int = field(default_factory=lambda: int(os.environ.get("AI_ORG_MAX_RUNS", "2")))
    max_turns: int | None = field(default_factory=lambda: int(os.environ.get("AI_ORG_MAX_TURNS", "30")))
    approval_timeout_s: float = field(
        default_factory=lambda: float(os.environ.get("AI_ORG_APPROVAL_TIMEOUT", "900"))
    )

    @property
    def upload_root(self) -> Path:
        return self.home / "uploads"

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.home / 'ai-org.db'}"

    @property
    def allowed_hosts(self) -> set[str]:
        return {"127.0.0.1", "localhost", "[::1]"}

    @property
    def allowed_origins(self) -> set[str]:
        origins: set[str] = set()
        for host in ("127.0.0.1", "localhost"):
            for port in (self.port, self.web_port):
                origins.add(f"http://{host}:{port}")
        return origins
