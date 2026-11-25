from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ai_org.config import Settings


def test_foreign_host_rejected(client: TestClient) -> None:
    res = client.get("/api/v1/system/health", headers={"host": "evil.example"})
    assert res.status_code == 403


def test_foreign_origin_rejected(client: TestClient) -> None:
    res = client.post("/api/v1/organizations", json={"name": "x"}, headers={"origin": "https://evil.example"})
    assert res.status_code == 403
    ok = client.post("/api/v1/organizations", json={"name": "x"}, headers={"origin": "http://localhost:3000"})
    assert ok.status_code == 201


def test_form_post_rejected(client: TestClient) -> None:
    res = client.post(
        "/api/v1/organizations",
        content="name=x",
        headers={"content-type": "application/x-www-form-urlencoded"},
    )
    assert res.status_code == 415


def test_system_info_reports_missing_claude(client: TestClient) -> None:
    info = client.get("/api/v1/system/info").json()
    claude = info["runtimes"][0]
    assert claude["id"] == "claude-code"
    assert claude["available"] is False


def test_capabilities_never_leak_secrets(client: TestClient, settings: Settings) -> None:
    skill = settings.claude_home / "skills" / "research"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("---\nname: research\ndescription: Web research\n---\nbody\n")
    (settings.claude_home.parent / ".claude.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    "github": {
                        "type": "http",
                        "url": "https://api.example.com/mcp?token=SECRET123",
                        "headers": {"Authorization": "Bearer SECRET123"},
                    },
                    "fs": {
                        "command": "/opt/bin/server-fs",
                        "args": ["--token", "SECRET123"],
                        "env": {"K": "SECRET123"},
                    },
                }
            }
        )
    )
    plugins = settings.claude_home / "plugins"
    plugins.mkdir()
    (plugins / "installed_plugins.json").write_text(
        json.dumps({"version": 2, "plugins": {"demo@market": [{"version": "1.0.0", "installPath": "/nope"}]}})
    )
    res = client.get("/api/v1/capabilities")
    assert res.status_code == 200
    assert "SECRET123" not in res.text
    caps = {c["id"]: c for c in res.json()}
    assert caps["skill:user:research"]["description"] == "Web research"
    assert caps["mcp:user:github"]["detail"]["host"] == "api.example.com"
    assert caps["mcp:user:fs"]["detail"] == {"command": "server-fs", "env_keys": 1}
    assert caps["plugin:demo@market"]["name"] == "demo"


def test_project_registration_confined_to_roots(client: TestClient, tmp_path: Path) -> None:
    root = tmp_path / "code"
    (root / "app" / ".git").mkdir(parents=True)
    (root / "app" / "package.json").write_text("{}")
    (root / "group" / "svc").mkdir(parents=True)
    (root / "group" / "svc" / "pyproject.toml").write_text("")
    (root / "node_modules" / "x").mkdir(parents=True)
    (root / "node_modules" / "x" / "package.json").write_text("{}")
    outside = tmp_path / "outside"
    outside.mkdir()

    assert client.post("/api/v1/project-roots", json={"path": "relative/path"}).status_code == 422
    assert client.post("/api/v1/project-roots", json={"path": "/"}).status_code == 422
    assert client.post("/api/v1/project-roots", json={"path": str(root)}).status_code == 201

    found = {c["name"]: c for c in client.get("/api/v1/project-roots/scan").json()}
    assert set(found) == {"app", "svc"}
    assert found["app"]["is_git"] is True and found["app"]["kind"] == "node"

    assert client.post("/api/v1/projects", json={"path": str(outside)}).status_code == 403
    # 심볼릭 링크로 등록 범위를 벗어날 수 없다.
    link = root / "escape"
    link.symlink_to(outside)
    assert client.post("/api/v1/projects", json={"path": str(link)}).status_code == 403

    res = client.post("/api/v1/projects", json={"path": str(root / "app")})
    assert res.status_code == 201
    detail = client.get(f"/api/v1/projects/{res.json()['id']}").json()
    assert detail["kind"] == "node"
    assert "git" in detail


def test_timestamps_are_utc_with_offset(client: TestClient) -> None:
    org = client.post("/api/v1/organizations", json={"name": "TZ"}).json()
    assert org["created_at"].endswith(("Z", "+00:00"))
    assert client.get("/api/v1/workspace").json()["activity"][0]["created_at"].endswith(("Z", "+00:00"))


def test_fake_runtime_is_opt_in(settings: Settings) -> None:
    from dataclasses import replace

    from ai_org.main import create_app

    with TestClient(
        create_app(replace(settings, runtime_override="fake")), base_url="http://127.0.0.1:8000"
    ) as c:
        claude = c.get("/api/v1/system/info").json()["runtimes"][0]
        assert claude["version"] == "fake" and "가짜" in claude["name"]


def test_folder_browse_stays_in_home(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    (home / "code" / "app" / ".git").mkdir(parents=True)
    (home / "code" / "app" / "package.json").write_text("{}")
    (home / ".secret").mkdir()
    (home / "notes.txt").write_text("파일은 보이지 않아야 한다")
    outside = tmp_path / "outside"
    outside.mkdir()
    (home / "escape").symlink_to(outside)
    monkeypatch.setenv("HOME", str(home))

    top = client.get("/api/v1/fs/browse").json()
    assert top["path"] == str(home.resolve()) and top["parent"] is None
    assert [e["name"] for e in top["entries"]] == ["code"]  # 숨김·파일·홈 밖 링크 제외
    hidden = client.get("/api/v1/fs/browse", params={"hidden": True}).json()
    assert [e["name"] for e in hidden["entries"]] == [".secret", "code"]

    code = client.get("/api/v1/fs/browse", params={"path": str(home / "code")}).json()
    assert code["parent"] == str(home.resolve())
    assert code["entries"][0] == {
        "name": "app",
        "path": str((home / "code" / "app").resolve()),
        "is_git": True,
        "kind": "node",
    }
    assert client.get("/api/v1/fs/browse", params={"path": str(outside)}).status_code == 403
    assert client.get("/api/v1/fs/browse", params={"path": str(home / "escape")}).status_code == 403
    assert client.get("/api/v1/fs/browse", params={"path": "relative"}).status_code == 422
