"""에이전트 권한 정책 → 런타임 설정·도구 결정.

원칙: 이 정책은 모든 도구 호출에 대해 PreToolUse 훅에서 먼저 평가된다(runtime/claude_code.py).
- deny: 즉시 거부. ask: 사용자 승인을 기다림. allow: 통과.
  allow는 둘로 나뉜다 — 명시적 허용(허용 리스트 일치)과 단순 통과(우리 정책이 막지 않음).
- 판단 순서(decide): ① 꺼 둔 도구 차단 ② 작업 폴더 밖 경로(파일 도구는 거부, 셸은 승인)
  ③ 허용 리스트 일치면 허용
  ④ (auto 모드가 아니면) require_approval 묶음은 승인 ⑤ 나머지는 통과.
  ①②는 허용 리스트·auto 모드보다 먼저라서 어떤 설정으로도 건너뛸 수 없다.
- 금지 도구 묶음은 disallowed_tools로도 아예 막는다(deny 규칙은 어떤 모드에서도 우선).
"""

from __future__ import annotations

import os
import re
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from ai_org.schemas import AgentPermissions
from ai_org.services import rules

SHELL_TOOLS = ("Bash", "BashOutput", "KillShell", "KillBash", "Monitor")
WRITE_TOOLS = ("Edit", "MultiEdit", "Write", "NotebookEdit")
NETWORK_TOOLS = ("WebFetch", "WebSearch")
PATH_KEYS = ("file_path", "notebook_path", "path")
DELETE_PATTERN = rules.DELETE_PATTERN

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
    슬래시 2개 이상으로만 된 인자(`//`, `///`)는 경로로 보지 않는다(#94). 루트를 가리키려고 `//`를 쓰는
    일은 사실상 없고, 주석 기호 검색(`grep -rn "//" src`)·구분자로 흔하다. 단일 `/`는 루트로 본다
    (`ls /`, `find / -name x`는 승인). `//etc/passwd`처럼 뒤에 이름이 붙으면 실제로 `/etc/passwd`이므로
    아래 판정대로 경로다.
    """
    if arg.startswith("~") or arg == ".." or arg.startswith("../") or "/../" in arg:
        return True
    if len(arg) >= 2 and arg.strip("/") == "":
        return False
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
            if _is_path_like(arg) or _may_expand_outside(arg) or _is_relative_path(arg, base):
                found.append((arg, base))
    return found


# 중괄호 확장 안에 `.`·`/`·`~`가 있는 형태(`.{.,}` → `..`, `{/etc,x}`).
BRACE_PATH = re.compile(r"\{[^}]*[./~][^}]*\}")
# `.`으로 시작하고 글롭 문자가 있는 경로 조각(`.?`·`.*`는 `..`과 일치할 수 있다).
DOT_GLOB = re.compile(r"(^|/)\.[^/]*[*?\[]")


def _may_expand_outside(arg: str) -> bool:
    """셸 확장 뒤에 작업 폴더 밖을 가리킬 수 있는 인자인가(정적으로 알 수 없으므로 '밖일 수 있음')."""
    return bool(BRACE_PATH.search(arg) or DOT_GLOB.search(arg))


def _is_relative_path(arg: str, base: Path | None) -> bool:
    """작업 폴더 기준 상대 경로로 볼 인자인가.

    `/`가 들어 있거나 실제로 있는 이름이면 경로로 보고 심볼릭 링크를 해석해 범위를 확인한다
    (`link/secret`처럼 폴더 안 링크가 밖을 가리키는 경우). 없는 이름은 경로로 보지 않는다.
    """
    # 절대 경로·`~`는 _is_path_like가 판정한다(`/status` 같은 검색어 오탐 방지 포함).
    if base is None or not arg or arg.startswith(("-", "/", "~")) or len(arg) > 1024 or "\x00" in arg:
        return False
    if "/" in arg:
        return True
    try:
        return os.path.lexists(base / arg)
    except OSError:
        return False


def outside_paths(command: str, roots: list[Path]) -> list[str]:
    out = []
    for raw, base in shell_paths(command, roots[0]):
        if raw in SAFE_DEVICES:
            continue
        if _may_expand_outside(raw):
            out.append(raw)
            continue
        target = Path(raw).expanduser()
        try:
            resolved = target.resolve() if target.is_absolute() else ((base or roots[0]) / target).resolve()
        except (OSError, RuntimeError):
            out.append(raw)  # 해석할 수 없는 경로(링크 순환 등)는 밖일 수 있다고 본다.
            continue
        if not within(resolved, roots):
            out.append(raw)
    return list(dict.fromkeys(out))  # 같은 값은 한 번만(순서 유지)


Group = Literal["shell", "file_write", "file_delete", "network", "delegate", "mcp"]


@dataclass(frozen=True)
class Verdict:
    action: Literal["allow", "deny", "ask"]
    group: Group | None = None
    reason: str = ""
    explicit: bool = False  # allow일 때: 허용 리스트에 맞아 명시적으로 허용됨(단순 통과와 구분)
    outside: bool = False  # 작업 폴더 밖 경로 때문에 내린 판정


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
        if isinstance(command, str) and rules.is_delete(command):
            return "file_delete"  # 대소문자·따옴표·`/bin/rm` 변형 포함
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


Source = Literal["hook", "runtime"]


def decide(
    perms: AgentPermissions,
    tool: str,
    tool_input: dict[str, Any],
    roots: list[Path],
    *,
    source: Source = "hook",
    mode: str | None = None,
) -> Verdict:
    """도구 호출을 판정한다.

    source: "hook"은 모든 도구 호출 전(PreToolUse),
    "runtime"은 Claude Code가 스스로 되물은 호출(can_use_tool).
    mode: 이 실행이 시작된 권한 모드(없으면 perms.permission_mode).
    """
    mode = mode or perms.permission_mode
    group = group_of(tool, tool_input)
    shell = group in ("shell", "file_delete")
    command = tool_input.get("command")

    # ① 꺼 둔 도구는 auto 모드여도, 허용 규칙이 있어도 쓸 수 없다.
    if shell and not perms.allow_shell:
        return Verdict("deny", group, "이 에이전트는 셸 명령을 실행할 수 없습니다.")
    if group == "file_delete" and not perms.allow_file_delete:
        return Verdict("deny", group, "이 에이전트는 파일을 삭제할 수 없습니다.")
    if group == "file_write" and not perms.allow_file_write:
        return Verdict("deny", group, "이 에이전트는 파일을 수정할 수 없습니다.")
    if group == "network" and not perms.allow_network:
        return Verdict("deny", group, "이 에이전트는 네트워크를 사용할 수 없습니다.")
    if group == "delegate" and not perms.can_delegate:
        return Verdict("deny", group, "이 에이전트는 하위 에이전트에 위임할 수 없습니다.")

    # ② 작업 폴더 밖 경로: 파일 도구는 거부, 셸은 항상 사람이 확인(허용 리스트·auto보다 먼저).
    # 경로성 인자 전부를 본다: file_path·notebook_path·path, Glob의 pattern, Grep의 glob.
    if rules.file_outside(tool, tool_input, roots):
        return Verdict("deny", group, "허용된 작업 범위 밖의 경로입니다.", outside=True)
    if shell:
        escaped = outside_paths(command, roots) if isinstance(command, str) and roots else []
        if escaped:
            verb = "삭제하려 합니다" if group == "file_delete" else "참조합니다"
            return Verdict(
                "ask",
                group,
                f"작업 폴더 밖 경로를 {verb}: " + ", ".join(f"'{p}'" for p in escaped[:3]),
                outside=True,
            )

    # ③ 허용 리스트에 맞으면 묻지 않는다(삭제·위임은 규칙 대상이 아니다).
    if group not in ("file_delete", "delegate"):
        matched = rules.match(perms.allow_rules, tool, tool_input, roots)
        if matched is not None:
            return Verdict("allow", group, f"허용 규칙 일치: {matched}", explicit=True)

    if mode == "auto":
        # auto: 묶음별 승인을 적용하지 않고 Claude Code의 판단에 맡긴다.
        # Claude Code가 되물은 호출만 앱 승인으로 사용자에게 묻는다.
        if source == "runtime":
            return Verdict("ask", group, "Claude Code가 확인을 요청했습니다.")
        return Verdict("allow", group)

    # ④ 묶음별 승인.
    if group is not None and group in perms.require_approval:
        return Verdict("ask", group)
    # ⑤ 읽기·검색 등 위험 묶음이 아닌 도구는 우리 정책이 막지 않는다.
    # (Claude Code가 자체 규칙으로 확인을 요청하면 그 판단은 그대로 유지된다.)
    return Verdict("allow", group)
