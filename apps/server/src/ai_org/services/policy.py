"""에이전트 권한 정책 → 런타임 설정·도구 결정.

원칙: 이 정책은 모든 도구 호출에 대해 PreToolUse 훅에서 먼저 평가된다(runtime/claude_code.py).
- deny: 즉시 거부. ask: 사용자 승인을 기다림. allow: 통과(그 뒤 Claude Code 자체 확인이 있으면 허용 처리).
- 금지 도구 묶음은 disallowed_tools로 아예 막는다(deny 규칙은 어떤 모드에서도 우선).
- 허용 범위 밖 경로를 대상으로 한 도구는 거부한다.
- require_approval 묶음은 사용자 승인을 받는다.
"""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from ai_org.schemas import AgentPermissions

SHELL_TOOLS = ("Bash", "BashOutput", "KillShell", "KillBash", "Monitor")
WRITE_TOOLS = ("Edit", "MultiEdit", "Write", "NotebookEdit")
NETWORK_TOOLS = ("WebFetch", "WebSearch")
PATH_KEYS = ("file_path", "notebook_path", "path")
DELETE_PATTERN = re.compile(r"(^|[\s;&|(])(rm|rmdir|unlink|shred)\s|git\s+clean\b|find\s.*-delete\b")

SAFE_DEVICES = {
    "/dev/null",
    "/dev/stdin",
    "/dev/stdout",
    "/dev/stderr",
    "/dev/tty",
    "/dev/zero",
    "/dev/urandom",
}
REDIRECT = re.compile(r"^(?:\d?>>?|<|&>)")
SEGMENT_SPLIT = re.compile(r"&&|\|\||[|;()]")


def _is_path_like(arg: str) -> bool:
    """경로 인자로 볼지.

    `/status` 같은 한 단계짜리 절대 문자열은 실제로 있을 때만 경로로 본다(검색어 오탐 방지).
    """
    if arg.startswith("~") or arg == ".." or arg.startswith("../") or "/../" in arg:
        return True
    if arg.startswith("/"):
        parts = [p for p in arg.split("/") if p]
        return len(parts) >= 2 or Path(arg).exists()
    return False


def shell_paths(command: str, cwd: Path | None = None) -> list[tuple[str, Path | None]]:
    """셸 명령에서 경로로 보이는 인자와 그 상대 경로의 기준 폴더를 찾는다.

    명령 이름 자리는 제외하고, 같은 명령 안의 `cd <폴더>`를 따라 이후 상대 경로의 기준을 바꾼다
    (`cd` 대상 자체도 검사 대상이다).
    """
    found: list[tuple[str, Path | None]] = []
    base = cwd
    for segment in SEGMENT_SPLIT.split(command):
        try:
            words = shlex.split(segment, comments=True)
        except ValueError:
            words = segment.split()
        while words and "=" in words[0] and not words[0].startswith(("/", "~", ".")):
            words = words[1:]  # VAR=value 접두사
        if not words:
            continue
        head, args = words[0], words[1:]
        if head == "cd" and args and base is not None:
            target = Path(args[0]).expanduser()
            found.append((args[0], base))
            base = (target if target.is_absolute() else base / target).resolve()
            continue
        for word in args:
            arg = REDIRECT.sub("", word)
            if "=" in arg and not arg.startswith(("/", "~", ".")):
                arg = arg.split("=", 1)[1]  # --out=/path
            if _is_path_like(arg):
                found.append((arg, base))
    return found


def outside_paths(command: str, roots: list[Path]) -> list[str]:
    out = []
    for raw, base in shell_paths(command, roots[0]):
        if raw in SAFE_DEVICES:
            continue
        target = Path(raw).expanduser()
        resolved = target.resolve() if target.is_absolute() else ((base or roots[0]) / target).resolve()
        if not within(resolved, roots):
            out.append(raw)
    return out


Group = Literal["shell", "file_write", "file_delete", "network", "delegate", "mcp"]


@dataclass(frozen=True)
class Verdict:
    action: Literal["allow", "deny", "ask"]
    group: Group | None = None
    reason: str = ""


def disallowed_tools(perms: AgentPermissions) -> tuple[str, ...]:
    tools: list[str] = []
    if not perms.allow_shell:
        tools += SHELL_TOOLS
    if not perms.allow_file_write:
        tools += WRITE_TOOLS
    if not perms.allow_network:
        tools += NETWORK_TOOLS
    return tuple(tools)


def group_of(tool: str, tool_input: dict[str, Any]) -> Group | None:
    if tool in SHELL_TOOLS:
        command = tool_input.get("command")
        if isinstance(command, str) and DELETE_PATTERN.search(command):
            return "file_delete"
        return "shell"
    if tool in WRITE_TOOLS:
        return "file_write"
    if tool in NETWORK_TOOLS:
        return "network"
    if tool in ("Agent", "Task") or tool.startswith("mcp__org__"):
        return "delegate"
    if tool.startswith("mcp__"):
        return "mcp"
    return None


def within(path: Path, roots: list[Path]) -> bool:
    return any(path == root or root in path.parents for root in roots)


def decide(perms: AgentPermissions, tool: str, tool_input: dict[str, Any], roots: list[Path]) -> Verdict:
    """Claude Code가 확인을 요청한 도구 호출을 판정한다."""
    group = group_of(tool, tool_input)
    for key in PATH_KEYS:
        raw = tool_input.get(key)
        if isinstance(raw, str) and raw:
            target = Path(raw).expanduser()
            resolved = target.resolve() if target.is_absolute() else (roots[0] / target).resolve()
            if not within(resolved, roots):
                return Verdict("deny", group, "허용된 작업 범위 밖의 경로입니다.")
    if group == "shell" and not perms.allow_shell:
        return Verdict("deny", group, "이 에이전트는 셸 명령을 실행할 수 없습니다.")
    if group in ("shell", "file_delete"):
        command = tool_input.get("command")
        escaped = outside_paths(command, roots) if isinstance(command, str) and roots else []
        if escaped and group == "shell" and perms.allow_shell:
            # 셸 허용 에이전트라도 작업 범위 밖 경로를 건드리는 명령은 항상 사람이 확인한다.
            return Verdict("ask", group, "작업 폴더 밖 경로를 참조합니다: " + ", ".join(escaped[:3]))
    if group == "file_delete" and not (perms.allow_shell and perms.allow_file_delete):
        return Verdict("deny", group, "이 에이전트는 파일을 삭제할 수 없습니다.")
    if group == "file_delete":
        command = tool_input.get("command")
        escaped = outside_paths(command, roots) if isinstance(command, str) and roots else []
        if escaped:
            return Verdict("ask", group, "작업 폴더 밖 경로를 삭제하려 합니다: " + ", ".join(escaped[:3]))
    if group == "file_write" and not perms.allow_file_write:
        return Verdict("deny", group, "이 에이전트는 파일을 수정할 수 없습니다.")
    if group == "network" and not perms.allow_network:
        return Verdict("deny", group, "이 에이전트는 네트워크를 사용할 수 없습니다.")
    if group == "delegate" and not perms.can_delegate:
        return Verdict("deny", group, "이 에이전트는 하위 에이전트에 위임할 수 없습니다.")
    if group is not None and group in perms.require_approval:
        return Verdict("ask", group)
    # 읽기·검색 등 위험 묶음이 아닌 도구는 경로 검사만 통과하면 우리 정책은 막지 않는다.
    # (Claude Code가 자체 규칙으로 확인을 요청하면 그 판단은 그대로 유지된다.)
    return Verdict("allow", group)
