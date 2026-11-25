from __future__ import annotations

from pathlib import Path

from ai_org.runtime.activity import classify, is_test_command
from ai_org.schemas import AgentPermissions
from ai_org.services import policy

ROOT = [Path("/work/app")]


def test_default_permissions_are_conservative() -> None:
    perms = AgentPermissions()
    assert "Bash" in policy.disallowed_tools(perms)
    assert policy.decide(perms, "Bash", {"command": "ls"}, ROOT).action == "deny"
    assert policy.decide(perms, "Read", {"file_path": "/work/app/a.py"}, ROOT).action == "allow"
    assert policy.decide(perms, "Read", {"file_path": "/home/u/.ssh/id_rsa"}, ROOT).action == "deny"
    assert policy.decide(perms, "Write", {"file_path": "../../etc/x"}, ROOT).action == "deny"
    assert policy.decide(perms, "Write", {"file_path": "src/x.py"}, ROOT).action == "ask"


def test_shell_requires_approval_even_for_read_only_commands() -> None:
    perms = AgentPermissions(allow_shell=True, require_approval=["shell"])
    assert policy.decide(perms, "Bash", {"command": "echo hi"}, ROOT).action == "ask"


def test_delete_detection() -> None:
    perms = AgentPermissions(allow_shell=True, require_approval=[])
    assert policy.decide(perms, "Bash", {"command": "rm -rf build"}, ROOT).action == "deny"
    perms = AgentPermissions(allow_shell=True, allow_file_delete=True, require_approval=["file_delete"])
    assert policy.decide(perms, "Bash", {"command": "cd x && rm a"}, ROOT).action == "ask"
    assert policy.decide(perms, "Bash", {"command": "git clean -fd"}, ROOT).group == "file_delete"


def test_delegate_and_mcp() -> None:
    assert policy.decide(AgentPermissions(), "Agent", {}, ROOT).action == "deny"
    assert (
        policy.decide(AgentPermissions(can_delegate=True, require_approval=[]), "Agent", {}, ROOT).action
        == "allow"
    )
    assert policy.decide(AgentPermissions(), "mcp__github__create_issue", {}, ROOT).action == "ask"


def test_activity_classification() -> None:
    assert classify("Read", {}) == "reading"
    assert classify("Edit", {}) == "coding"
    assert classify("WebSearch", {}) == "browsing"
    assert classify("TodoWrite", {}) == "planning"
    assert classify("Bash", {"command": "cd apps/web && npm test"}) == "testing"
    assert classify("Bash", {"command": "ls -la"}) == "unknown"
    assert is_test_command("uv run pytest -q")
    assert is_test_command("python -m pytest tests")
    assert is_test_command("CI=1 npx vitest run")
    assert not is_test_command("npm install")
