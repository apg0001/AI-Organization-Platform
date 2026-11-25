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
        usage_poll_s=0,
    )


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings), base_url="http://127.0.0.1:8000") as c:
        yield c
