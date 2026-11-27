from __future__ import annotations

from pathlib import Path

import pytest

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


def test_shell_paths_outside_scope_require_approval() -> None:
    perms = AgentPermissions(allow_shell=True, require_approval=[])
    assert policy.decide(perms, "Bash", {"command": "npm test"}, ROOT).action == "allow"
    assert policy.decide(perms, "Bash", {"command": "ls src && cat ./README.md"}, ROOT).action == "allow"
    assert (
        policy.decide(perms, "Bash", {"command": "/usr/bin/python3 -m pytest /work/app/tests"}, ROOT).action
        == "allow"
    )
    assert policy.decide(perms, "Bash", {"command": "echo hi > /dev/null 2>&1"}, ROOT).action == "allow"
    for cmd in (
        "cat ~/.ssh/id_rsa",
        "cp out.txt /etc/hosts",
        "echo x >/tmp/leak",
        "cd .. && ls",
        "tar czf x.tgz ../../secret",
        "curl --output=/home/u/x http://e",
        "FOO=1 grep -r token /home",
    ):
        verdict = policy.decide(perms, "Bash", {"command": cmd}, ROOT)
        assert verdict.action == "ask", cmd
        assert "작업 폴더 밖" in verdict.reason


def test_shell_disabled_still_denied_before_path_check() -> None:
    assert policy.decide(AgentPermissions(), "Bash", {"command": "cat /etc/passwd"}, ROOT).action == "deny"


def test_delete_outside_scope_asks_even_when_delete_allowed() -> None:
    perms = AgentPermissions(allow_shell=True, allow_file_delete=True, require_approval=[])
    assert policy.decide(perms, "Bash", {"command": "rm -rf build"}, ROOT).action == "allow"
    assert policy.decide(perms, "Bash", {"command": "rm -rf ~/Documents"}, ROOT).action == "ask"


def test_shell_path_false_positives_from_dogfooding(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    (root / "apps" / "server").mkdir(parents=True)
    (root / "docs").mkdir()
    roots = [root]
    perms = AgentPermissions(allow_shell=True, require_approval=[])
    # 검색어는 경로가 아니다.
    assert policy.decide(perms, "Bash", {"command": 'grep -rn "/status" docs'}, roots).action == "allow"
    assert policy.decide(perms, "Bash", {"command": "git grep -n /status"}, roots).action == "allow"
    # 같은 명령 안의 cd를 따라 상대 경로 기준을 바꾼다.
    assert (
        policy.decide(
            perms, "Bash", {"command": "cd apps/server && grep -rln status ../../docs"}, roots
        ).action
        == "allow"
    )
    # 그래도 범위 밖은 승인 요청.
    assert (
        policy.decide(perms, "Bash", {"command": "cd apps/server && cat ../../../secret"}, roots).action
        == "ask"
    )
    assert policy.decide(perms, "Bash", {"command": "cd /etc && cat hostname"}, roots).action == "ask"
    assert (
        policy.decide(perms, "Bash", {"command": "grep x /home"}, roots).action == "ask"
    )  # 실제로 있는 경로


# ── #94: 슬래시만으로 된 인자(`//`) 오탐, 사유 중복 ─────────────────────────


@pytest.mark.parametrize(
    "command",
    [
        'grep -rn "//" src',
        "grep -n '//' a.ts",
        'rg "//"',
        "rg '//\\s*TODO' src",
        'grep -E "^//" a.ts',
        "sed 's#//#/#' a.txt",
        "echo ///",
    ],
)
def test_slash_only_arguments_are_not_paths(tmp_path: Path, command: str) -> None:
    root = tmp_path / "repo"
    (root / "src").mkdir(parents=True)
    (root / "a.ts").write_text("// x")
    (root / "a.txt").write_text("a//b")
    perms = AgentPermissions(allow_shell=True, require_approval=[])
    assert policy.outside_paths(command, [root]) == [], command
    verdict = policy.decide(perms, "Bash", {"command": command}, [root])
    assert verdict.action == "allow" and verdict.outside is False, command


@pytest.mark.parametrize(
    ("command", "escaped"),
    [
        ("ls /", ["/"]),
        ("find / -name x", ["/"]),
        ("cat //etc/passwd", ["//etc/passwd"]),
        ("cat /etc/passwd", ["/etc/passwd"]),
        ("ls ~", ["~"]),
    ],
)
def test_root_and_absolute_paths_still_ask(tmp_path: Path, command: str, escaped: list[str]) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    perms = AgentPermissions(allow_shell=True, require_approval=[])
    assert policy.outside_paths(command, [root]) == escaped
    verdict = policy.decide(perms, "Bash", {"command": command}, [root])
    assert verdict.action == "ask" and verdict.outside is True


def test_outside_reason_is_deduplicated_and_quoted(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    perms = AgentPermissions(allow_shell=True, require_approval=[])
    command = "cat /etc/passwd /etc/passwd /etc/hosts"
    assert policy.outside_paths(command, [root]) == ["/etc/passwd", "/etc/hosts"]
    verdict = policy.decide(perms, "Bash", {"command": command}, [root])
    assert verdict.reason == "작업 폴더 밖 경로를 참조합니다: '/etc/passwd', '/etc/hosts'"


def test_slash_search_always_rule_is_exact(tmp_path: Path) -> None:
    from ai_org.services import rules

    root = tmp_path / "repo"
    (root / "src").mkdir(parents=True)
    rule, reason = rules.suggest("Bash", {"command": 'grep -rn "//" src'}, [root], group="shell")
    assert rule == 'Bash(grep -rn "//" src)' and reason == ""  # 명령 전체 일치(따옴표 그대로)
    # 규칙은 같은 명령만 열고, 같은 접두의 폴더 밖 검색은 여전히 묻는다.
    perms = AgentPermissions(allow_shell=True, allow_rules=[rule], require_approval=["shell"])
    assert policy.decide(perms, "Bash", {"command": 'grep -rn "//" src'}, [root]).explicit is True
    assert policy.decide(perms, "Bash", {"command": 'grep -rn "//" /etc'}, [root]).action == "ask"
    assert policy.decide(perms, "Bash", {"command": 'grep -rn "//" lib'}, [root]).action == "ask"
