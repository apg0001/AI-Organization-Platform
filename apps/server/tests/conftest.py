from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ai_org.config import Settings
from ai_org.main import create_app


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    claude_home = tmp_path / "claude-home" / ".claude"
    claude_home.mkdir(parents=True)
    return Settings(
        home=tmp_path / "data",
        claude_home=claude_home,
        claude_bin="definitely-not-claude",
        auth_enabled=False,
        # 포트를 고정한다: 지정하지 않으면 AI_ORG_PORT·AI_ORG_WEB_PORT 환경 변수를 읽어
        # 허용 Origin이 달라지고, 그 변수가 잡힌 셸에서 Origin 테스트가 실패한다.
        port=8000,
        web_port=3000,
        usage_poll_s=0,
    )


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings), base_url="http://127.0.0.1:8000") as c:
        yield c
