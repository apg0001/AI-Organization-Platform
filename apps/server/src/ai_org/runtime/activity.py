"""도구 사용 → 활동 분류와 짧은 대상 요약.

분류 규칙은 Agent Office Collector(collector/core/internal/adapter/claude/claude.go toolCategory,
adapter/command.go 테스트 명령 판별)를 Python으로 옮긴 것이다(MIT). 사무실 구역과 활동 패널이 쓴다.
"""

from __future__ import annotations

import re
import shlex
from typing import Any

Activity = str  # reading | coding | browsing | testing | planning | delegating | asking | unknown

_TOOL_ACTIVITY = {
    "Read": "reading",
    "Grep": "reading",
    "Glob": "reading",
    "LS": "reading",
    "Edit": "coding",
    "MultiEdit": "coding",
    "Write": "coding",
    "NotebookEdit": "coding",
    "WebSearch": "browsing",
    "WebFetch": "browsing",
    "Agent": "delegating",
    "Task": "delegating",
    "TodoWrite": "planning",
    "ExitPlanMode": "planning",
    "EnterPlanMode": "planning",
    "AskUserQuestion": "asking",
}

_TEST_RUNNERS = {"pytest", "vitest", "jest", "mocha", "ava", "tap", "phpunit", "rspec", "ctest", "tox", "nox"}
_TEST_SUBCOMMANDS = {"go", "cargo", "npm", "yarn", "pnpm", "bun", "make", "dotnet", "mvn", "gradle", "deno"}
_WRAPPERS = {"sudo", "env", "npx", "time", "nice", "uv", "poetry", "pipenv", "bunx"}
_SPLIT = re.compile(r"&&|\|\||[|;()]")


def is_test_command(command: str) -> bool:
    for part in _SPLIT.split(command):
        try:
            words = shlex.split(part)
        except ValueError:
            words = part.split()
        words = [w for w in words if "=" not in w or w.startswith("-")]
        while words and (words[0] in _WRAPPERS or words[0] in {"run", "exec"}):
            words = words[1:]
        if not words:
            continue
        head = words[0].rsplit("/", 1)[-1]
        if head in _TEST_RUNNERS or (head == "python" and words[1:3] == ["-m", "pytest"]):
            return True
        if head in _TEST_SUBCOMMANDS and len(words) > 1 and words[1] in {"test", "t"}:
            return True
        if head in _TEST_SUBCOMMANDS and len(words) > 2 and words[1] == "run" and words[2].startswith("test"):
            return True
    return False


def classify(tool: str, tool_input: dict[str, Any]) -> Activity:
    if tool == "Bash":
        command = tool_input.get("command")
        return "testing" if isinstance(command, str) and is_test_command(command) else "unknown"
    if tool.startswith("mcp__org__"):
        return "delegating"
    if tool.startswith("mcp__"):
        return "unknown"
    return _TOOL_ACTIVITY.get(tool, "unknown")


def target_of(tool: str, tool_input: dict[str, Any], limit: int = 120) -> str:
    """활동 패널에 보여 줄 짧은 대상(경로·명령·검색어). 파일 내용이나 전체 출력은 넣지 않는다."""
    keys = (
        "file_path",
        "notebook_path",
        "path",
        "pattern",
        "query",
        "url",
        "command",
        "assignee",
        "reviewer",
        "description",
    )
    for key in keys:
        value = tool_input.get(key)
        if isinstance(value, str) and value:
            single = " ".join(value.split())
            return single if len(single) <= limit else single[: limit - 1] + "…"
    return ""
