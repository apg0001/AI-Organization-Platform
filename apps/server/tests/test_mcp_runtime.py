from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from ai_org.config import Settings
from ai_org.schemas import AgentPermissions
from ai_org.services import policy
from ai_org.services.capabilities import parse_mcp_list, resolve_mcp_servers, resolve_plugin_paths
from tests.test_chat import FakeRuntime, wait_message

MCP = {
    "mcpServers": {
        "github": {
            "type": "http",
            "url": "https://api.example.com/mcp",
            "headers": {"Authorization": "Bearer SECRET9"},
        },
        "fs": {"command": "server-fs", "env": {"TOKEN": "SECRET9"}},
    }
}


def write_home(settings: Settings, tmp_path: Path) -> Path:
    (settings.claude_home.parent / ".claude.json").write_text(json.dumps(MCP))
    plugin_dir = tmp_path / "plugin-a"
    (plugin_dir / ".claude-plugin").mkdir(parents=True)
    (plugin_dir / ".claude-plugin" / "plugin.json").write_text('{"name":"a"}')
    plugins = settings.claude_home / "plugins"
    plugins.mkdir()
    (plugins / "installed_plugins.json").write_text(
        json.dumps(
            {"plugins": {"a@m": [{"installPath": str(plugin_dir)}], "b@m": [{"installPath": "/nope"}]}}
        )
    )
    return plugin_dir


def test_resolve_only_allowed(settings: Settings, tmp_path: Path) -> None:
    plugin_dir = write_home(settings, tmp_path)
    project = tmp_path / "proj"
    project.mkdir()
    (project / ".mcp.json").write_text(
        json.dumps({"mcpServers": {"chrome-devtools": {"command": "npx", "args": ["x"]}}})
    )
    servers = resolve_mcp_servers(
        settings.claude_home,
        [str(project)],
        ["mcp:user:github", "mcp:project:chrome-devtools", "mcp:user:missing"],
    )
    assert set(servers) == {"github", "chrome-devtools"}
    assert servers["github"]["headers"]["Authorization"] == "Bearer SECRET9"  # 실행 옵션에는 원본이 필요
    assert (
        resolve_mcp_servers(settings.claude_home, [], ["mcp:local:github"]) == {}
    )  # 범위가 다르면 안 붙는다
    assert resolve_plugin_paths(settings.claude_home, ["plugin:a@m", "plugin:b@m"]) == [str(plugin_dir)]


def test_run_request_carries_allowed_mcp_and_plugins(
    client: TestClient, settings: Settings, tmp_path: Path
) -> None:
    write_home(settings, tmp_path)
    fake = FakeRuntime()
    from ai_org.main import create_app

    with TestClient(
        create_app(settings, runtime_for=lambda _id: fake), base_url="http://127.0.0.1:8000"
    ) as api:
        org = api.post("/api/v1/organizations", json={"name": "M"}).json()
        ceo = org["agents"][0]
        api.patch(
            f"/api/v1/organizations/{org['id']}/agents/{ceo['id']}",
            json={"allowed_mcp_servers": ["mcp:user:github"], "allowed_plugins": ["plugin:a@m"]},
        )
        conv = api.post("/api/v1/conversations", json={"organization_id": org["id"]}).json()
        res = api.post(f"/api/v1/conversations/{conv['id']}/messages", json={"content": "hi"})
        wait_message(api, conv["id"], res.json()["assistant_message_ids"][0])
        req = fake.requests[-1]
        assert set(req.mcp_servers) == {"github"} and len(req.plugin_paths) == 1
        # API 응답에는 여전히 비밀이 없다.
        assert "SECRET9" not in api.get("/api/v1/capabilities").text
        assert "SECRET9" not in api.get(f"/api/v1/conversations/{conv['id']}").text


def test_mcp_tools_follow_mcp_approval_group() -> None:
    root = [Path("/work")]
    assert policy.decide(AgentPermissions(), "mcp__github__create_issue", {}, root).action == "ask"
    no_ask = AgentPermissions(require_approval=[])
    assert policy.decide(no_ask, "mcp__github__create_issue", {}, root).action == "allow"


def test_parse_mcp_list() -> None:
    out = """Checking MCP server health…

claude.ai Claude Docs: https://api.anthropic.com/v1/pages/mcp - ✔ Connected
chrome-devtools: npx -y chrome-devtools-mcp@1.14.0 --headless - ⏸ Pending approval (run `claude` to approve)
gh: https://x/mcp - ! Needs authentication
broken: node s.js - ✘ Failed to connect
"""
    states = {r["name"]: r["state"] for r in parse_mcp_list(out)}
    assert states == {
        "claude.ai Claude Docs": "connected",
        "chrome-devtools": "pending_approval",
        "gh": "needs_auth",
        "broken": "failed",
    }
