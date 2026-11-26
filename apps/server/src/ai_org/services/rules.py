"""에이전트별 허용 리스트(allow_rules): 규칙 파싱·검증·매칭·'항상 허용' 규칙 생성.

Claude Code 규칙 문법 중 이 앱이 안전하게 판정할 수 있는 부분만 지원한다.
- `Bash(접두:*)`  명령이 접두와 같거나 `접두 + 공백`으로 시작(단어 경계)
- `Bash(명령 전체)` 정확히 일치
- `Read(글롭)`     Read·Grep·Glob의 경로(작업 폴더 기준 상대 경로)
- `Edit(글롭)`·`Write(글롭)` 쓰기 도구 묶음(Edit·MultiEdit·Write·NotebookEdit)의 경로
- `WebSearch`·`WebFetch`·`mcp__서버__도구` 단독

원칙: 판단이 애매하면 '불일치'로 본다(= 평소대로 사용자에게 묻는다). 규칙은 승인을 줄일 뿐이고,
꺼 둔 도구 차단·작업 폴더 밖 판정은 policy.decide()가 규칙보다 먼저 한다.
접두 규칙은 '그 뒤에 무엇이 와도 안전한' 명령에만 허용한다. 다른 명령을 실행할 수 있는 도구
(인터프리터, find·xargs·sed 등, `git`·`npm` 단독, `uv run` 등 대리 실행)는 명령 전체 일치로만 저장된다.
이 모듈은 policy를 import하지 않는다(policy가 이 모듈을 쓴다).
"""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

MAX_RULES = 50
MAX_RULE_LENGTH = 200

READ_RULE_TOOLS = ("Read", "Grep", "Glob")
WRITE_RULE_TOOLS = ("Edit", "MultiEdit", "Write", "NotebookEdit")
PLAIN_TOOLS = ("WebSearch", "WebFetch")
PATH_KEYS = ("file_path", "notebook_path", "path")

# 삭제로 보는 명령(policy도 이 식을 쓴다). 허용 리스트로는 삭제를 열 수 없다.
# 대소문자를 가리지 않고, `/bin/rm`·`/usr/bin/rm`처럼 실행 파일 경로가 붙은 형태도 잡는다.
DELETE_PATTERN = re.compile(
    r"(^|[\s;&|(])(?:/[\w./-]*bin/)?(rm|rmdir|unlink|shred)\s|git\s+clean\b|find\s.*-delete\b", re.I
)
DANGER_WORDS = frozenset({"rm", "rmdir", "unlink", "shred", "sudo"})
# 셸·eval. 명령 어디에든(인자·따옴표 안 포함) 나오면 다른 명령을 실행할 수 있다고 본다(`sh -c …`).
SHELL_NAMES = frozenset({"bash", "sh", "zsh", "dash", "ksh", "fish", "csh", "tcsh", "eval"})
# 다른 명령을 실행하거나 파일을 지우는 인자(find의 -exec 등).
EXEC_FLAGS = frozenset({"-exec", "-execdir", "-ok", "-okdir", "-delete"})
# git에서 설정·실행 경로를 바꾸거나 외부 명령을 부르는 옵션(alias로 push를 숨기는 등).
# `--output`은 파일을 쓴다(`git diff --output=x`가 파일 쓰기 승인을 건너뛰지 않게).
GIT_UNSAFE_OPTIONS = (
    "--config-env",
    "--exec-path",
    "--exec",
    "--extcmd",
    "--upload-pack",
    "--receive-pack",
    "--output",
)
# 명령 안에서 경로·인자를 바꾸는 셸 확장 문법. 정적으로 판정할 수 없어 규칙과 대조하지 않는다.
EXPANSION_CHARS = ("{", "}", "*", "?", "[", "]", "(", ")")
# 물결표 확장은 단어 첫머리(또는 `=`·`:` 뒤)에서만 일어난다. `HEAD~1` 같은 인자는 확장이 아니다.
TILDE = re.compile(r"(^|[\s=:])~")

# 다른 명령을 대신 실행해 주는 명령. 규칙의 첫 단어가 되면(전체 일치여도) 사실상 셸 전체가 열린다.
WRAPPER_HEADS = frozenset(
    {
        "bash",
        "sh",
        "zsh",
        "dash",
        "ksh",
        "fish",
        "csh",
        "tcsh",
        "eval",
        "exec",
        "env",
        "xargs",
        "su",
        "doas",
        "command",
        "builtin",
        "nohup",
        "time",
        "timeout",
        "nice",
        "watch",
    }
)
# 임의 코드를 실행하는 인터프리터: 접두 규칙 불가(명령 전체 일치만).
INTERPRETERS = re.compile(r"^(python|pypy|node|deno|ruby|perl|php|lua|rscript|tsx|ts-node)[0-9.]*$")
# 인자에 따라 다른 명령을 실행하거나(-exec, e 플래그, system(), --to-command, ProxyCommand, 셸 탈출)
# 임의 파일을 덮어쓸 수 있는 도구: 접두 규칙 불가(명령 전체 일치만).
EXEC_CAPABLE = frozenset(
    {
        "find",  # -exec, -delete
        "fd",  # --exec
        "sed",  # e 명령, w 파일 쓰기, -i
        "awk",  # system()
        "gawk",
        "mawk",
        "nawk",
        "tar",  # --to-command, --checkpoint-action=exec
        "zip",  # -TT
        "ssh",  # 원격 명령, ProxyCommand
        "scp",
        "rsync",  # -e
        "parallel",
        "tee",  # 임의 파일 덮어쓰기
        "dd",
        "mv",  # 덮어쓰기로 삭제와 같은 효과
        "cp",
        "ln",
        "install",
        "truncate",
        "vi",  # 셸 탈출(:!)
        "vim",
        "nvim",
        "emacs",
        "ed",
        "less",
        "more",
        "man",
        "gdb",
        "strace",
        "script",
        "flock",
        "setsid",
        "stdbuf",
        "busybox",
        "tmux",
        "screen",
        "crontab",
        "at",
    }
)
# 하위 명령을 갖는 도구: 접두 규칙은 하위 명령까지 지정해야 한다(`Bash(git status:*)`).
SUBCOMMAND_TOOLS = frozenset(
    {
        "git",
        "npm",
        "pnpm",
        "yarn",
        "npx",
        "bun",
        "bunx",
        "cargo",
        "pip",
        "pip3",
        "pipx",
        "uv",
        "poetry",
        "docker",
        "podman",
        "kubectl",
        "helm",
        "make",
        "go",
        "gh",
        "apt",
        "apt-get",
        "brew",
        "gem",
        "conda",
        "systemctl",
        "terraform",
    }
)
# `npm run <스크립트>`처럼 스크립트 이름까지 봐야 하는 도구(세 단어 기준).
SCRIPT_RUNNERS = frozenset({"npm", "pnpm", "yarn", "bun"})
# 다른 프로그램을 대신 실행하는 하위 명령(`uv run …`, `docker exec …`): 접두 규칙 불가.
EXEC_SUBCOMMANDS = frozenset({"run", "exec", "dlx", "x"})
# 다른 명령을 실행하거나 설정(alias 등)을 바꿀 수 있는 git 하위 명령: 접두 규칙 불가.
GIT_EXEC_SUBCOMMANDS = frozenset(
    {"config", "submodule", "bisect", "rebase", "filter-branch", "difftool", "mergetool"}
)
# 패키지를 내려받아 바로 실행하는 도구(`npx tsx a.ts`): 두 번째 단어가 인터프리터·실행 도구면 접두 규칙 불가,
# '항상 허용'은 언제나 명령 전체 일치로 만든다.
PACKAGE_RUNNERS = frozenset({"npx", "bunx", "pipx"})
# 패키지 관리 도구와, 설치 스크립트 실행·의존성 변경으로 이어지는 하위 명령: 접두 규칙 불가
# (`npm install:*`이면 `npm install https://x/y.tgz`의 설치 스크립트가 묻지 않고 실행된다).
PACKAGE_TOOLS = frozenset(
    {
        "npm",
        "pnpm",
        "yarn",
        "bun",
        "pip",
        "pip3",
        "uv",
        "poetry",
        "cargo",
        "go",
        "gem",
        "brew",
        "apt",
        "apt-get",
        "conda",
    }
)
PACKAGE_SUBCOMMANDS = frozenset(
    {
        "install",
        "i",
        "add",
        "ci",
        "install-test",
        "it",
        "reinstall",
        "update",
        "upgrade",
        "up",
        "dist-upgrade",
        "full-upgrade",
        "remove",
        "uninstall",
        "un",
        "publish",
        "link",
        "create",
        "init",
        "rebuild",
        "get",
        "generate",
        "sync",
        "pip",
        "tool",
        "tap",
        "download",
    }
)
PLAIN_WORD = re.compile(r"^[A-Za-z0-9_./:@+=,-]+$")

# 규칙 본문에 올 수 없는 셸 문법(연결·치환·리다이렉션·변수 확장·묶음).
RULE_FORBIDDEN = ("&", "|", ";", "$", "`", ">", "<", "\n", "\r", "(", ")", "{", "}")
# 명령에 있으면 규칙과 대조하지 않는 문법(치환·변수 확장·리다이렉션·줄바꿈).
COMMAND_OPAQUE = ("$", "`", "<", ">", "\n", "\r")
SEGMENT_SPLIT = re.compile(r"&&|\|\||[;|&]")
RULE_FORM = re.compile(r"^([A-Za-z_][A-Za-z0-9_-]*)(?:\((.*)\))?$", re.S)
MCP_TOOL = re.compile(r"^mcp__[A-Za-z0-9_-]+?__[A-Za-z0-9_-]+$")
ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")

RuleKind = Literal["shell_prefix", "shell_exact", "read", "write", "tool"]


class RuleError(ValueError):
    """저장할 수 없는 규칙. 메시지는 사용자에게 그대로 보인다."""


@dataclass(frozen=True)
class Rule:
    kind: RuleKind
    pattern: str  # 셸: 접두·명령 전체 / 파일: 글롭 / 단독 도구: 도구 이름
    text: str  # 정리된 규칙 문자열(저장 형태)


def _words(text: str) -> list[str]:
    try:
        return shlex.split(text)
    except ValueError:
        return text.split()


def _name(word: str) -> str:
    """명령 단어의 이름: 경로를 떼고 소문자로(`/usr/bin/SUDO` → `sudo`)."""
    return word.rsplit("/", 1)[-1].lower()


def _plain(command: str) -> str:
    """따옴표·백슬래시를 지우고 소문자로 바꾼 명령(`'r''m'`·`\\rm`·`"RM"` 같은 변형을 한 형태로 본다)."""
    return re.sub(r"['\"\\]", "", command).lower()


def _tokens(command: str) -> list[str]:
    """위험 단어 검사용 토큰: 인자 안의 문자열까지 풀어 `=`·`:`·`,`로도 나누고 경로는 이름만 남긴다."""
    return [t.rsplit("/", 1)[-1] for t in re.split(r"[\s=:,;&|()<>{}]+", _plain(command)) if t]


def is_delete(command: str) -> bool:
    """삭제 명령인가(대소문자·따옴표·백슬래시 변형 포함)."""
    return bool(DELETE_PATTERN.search(command) or DELETE_PATTERN.search(_plain(command)))


def unsafe(command: str) -> str | None:
    """명령(또는 규칙 본문)이 허용 리스트로 다룰 수 없는 것이면 그 이유.

    저장 검증·매칭·규칙 생성이 모두 이 함수를 쓴다(저장되는 규칙은 매칭에서도 같은 기준을 지나도록).
    """
    tokens = _tokens(command)
    for name in tokens:
        if name in DANGER_WORDS:
            return f"`{name}` 명령은 허용 규칙에 넣을 수 없습니다."
    if "git" in tokens and "push" in tokens:
        return "`git push`는 허용 규칙에 넣을 수 없습니다."
    if is_delete(command) or is_delete(command + " "):
        return "파일을 삭제하는 명령은 허용 규칙에 넣을 수 없습니다."
    for name in tokens:
        if name in SHELL_NAMES:
            return f"`{name}`로 다른 명령을 실행하는 명령은 허용 규칙에 넣을 수 없습니다."
        if name in EXEC_FLAGS:
            return f"`{name}`가 있는 명령은 허용 규칙에 넣을 수 없습니다(다른 명령 실행·삭제)."
    if any(ch in command for ch in EXPANSION_CHARS) or TILDE.search(command):
        return "셸 확장 문법(`{}` `*` `?` `[]` `()` `~`)이 있는 명령은 허용 규칙에 넣을 수 없습니다."
    words = _words(command)
    if words and _name(words[0]) == "git":
        rest = words[1:]
        if (
            (rest and rest[0].startswith("-"))
            or any(w in ("-c", "-C") for w in rest)
            or any(w.lower().startswith(GIT_UNSAFE_OPTIONS) for w in rest)
            or "alias." in _plain(command)
        ):
            return "git 설정·실행 경로를 바꾸는 옵션(-c, -C, alias 등)이 있으면 허용 규칙에 넣을 수 없습니다."
    return None


def _prefix_problem(words: list[str]) -> str | None:
    """접두 규칙(`:*`)으로 저장할 수 없는 명령이면 그 이유. 명령 전체 일치로는 저장할 수 있다."""
    name = _name(words[0])
    hint = " 접두 규칙 대신 `Bash(명령 전체)`처럼 명령 전체를 적으세요."
    if INTERPRETERS.match(name):
        return f"`{name}`는 임의 코드를 실행하므로 접두 규칙으로 열 수 없습니다." + hint
    if name in EXEC_CAPABLE:
        return f"`{name}`는 다른 명령을 실행하거나 파일을 덮어쓸 수 있어 접두 규칙으로 열 수 없습니다." + hint
    if name not in SUBCOMMAND_TOOLS:
        return None
    if len(words) == 1:
        return f"`{name}` 접두 규칙은 하위 명령까지 지정해야 합니다(예: `Bash({name} <하위 명령>:*)`)." + hint
    sub = words[1].lower()
    if sub.startswith("-"):
        return f"`{name}` 접두 규칙은 옵션이 아니라 하위 명령으로 시작해야 합니다." + hint
    if name == "git" and sub in GIT_EXEC_SUBCOMMANDS:
        return f"`git {sub}`는 다른 명령을 실행할 수 있어 접두 규칙으로 열 수 없습니다." + hint
    if name in PACKAGE_RUNNERS:
        package = _name(sub).split("@")[0]  # `tsx@latest`, `@scope/tsx` → tsx
        if (
            INTERPRETERS.match(package)
            or package in EXEC_CAPABLE
            or package in WRAPPER_HEADS
            or package in SHELL_NAMES
        ):
            return f"`{name} {sub}`는 임의 코드를 실행하므로 접두 규칙으로 열 수 없습니다." + hint
    if name in PACKAGE_TOOLS and sub in PACKAGE_SUBCOMMANDS:
        return (
            f"`{name} {sub}`는 패키지를 설치·변경하며 설치 스크립트를 실행할 수 있어 접두 규칙으로 못 엽니다."
            + hint
        )
    if sub in EXEC_SUBCOMMANDS and name != "make":
        if sub == "run" and name in SCRIPT_RUNNERS and len(words) >= 3 and not words[2].startswith("-"):
            return None  # `npm run <스크립트>`는 스크립트 이름까지 고정된다.
        return f"`{name} {sub}`는 다른 프로그램을 대신 실행하므로 접두 규칙으로 열 수 없습니다." + hint
    return None


def _parse_shell(body: str | None) -> Rule:
    whole = "셸 전체를 여는 규칙은 저장할 수 없습니다. `Bash(npm test:*)`처럼 명령을 지정하세요."
    if body is None:
        raise RuleError(whole)
    content = body.strip()
    for token in RULE_FORBIDDEN:  # 공백 정리 전에 본다(줄바꿈이 공백으로 바뀌기 전에).
        if token in content:
            shown = "줄바꿈" if token in ("\n", "\r") else f"`{token}`"
            raise RuleError(f"셸 규칙에는 {shown}을(를) 쓸 수 없습니다(명령 연결·치환·리다이렉션·묶음 금지).")
    prefix = content.endswith(":*")
    command = " ".join((content[:-2] if prefix else content).split())
    if not command or command.strip("*: ") == "":
        raise RuleError(whole)
    if "*" in command:
        raise RuleError("`*`는 규칙 끝의 `:*`(접두 일치)로만 쓸 수 있습니다.")
    words = _words(command)
    if not words:
        raise RuleError(whole)
    head = _name(words[0])
    if ASSIGNMENT.match(words[0]):
        raise RuleError("셸 규칙은 `변수=값`으로 시작할 수 없습니다.")
    if head in WRAPPER_HEADS:
        raise RuleError(f"`{head}`는 다른 명령을 대신 실행하므로 허용 규칙에 넣을 수 없습니다.")
    if (reason := unsafe(command)) is not None:
        raise RuleError(reason)
    if prefix:
        if (reason := _prefix_problem(words)) is not None:
            raise RuleError(reason)
        return Rule("shell_prefix", command, f"Bash({command}:*)")
    return Rule("shell_exact", command, f"Bash({command})")


def _parse_glob(tool: str, body: str | None) -> Rule:
    glob = (body or "").strip()
    if not glob:
        raise RuleError(f"`{tool}` 규칙에는 경로가 필요합니다. 예: `{tool}(src/**)`")
    while glob.startswith("./"):
        glob = glob[2:]
    if not glob or glob.startswith(("/", "~")):
        raise RuleError("파일 규칙은 작업 폴더 기준 상대 경로만 쓸 수 있습니다(`/`·`~`로 시작할 수 없음).")
    if ".." in glob.split("/") or "\\" in glob or "\n" in glob:
        raise RuleError("파일 규칙에는 `..`을 쓸 수 없습니다(작업 폴더 밖은 허용할 수 없음).")
    kind: RuleKind = "read" if tool == "Read" else "write"
    return Rule(kind, glob, f"{tool}({glob})")


def parse(raw: str) -> Rule:
    """규칙 문자열을 검증해 Rule로 만든다. 저장할 수 없으면 RuleError."""
    text = raw.strip() if isinstance(raw, str) else ""
    if not text:
        raise RuleError("빈 규칙은 저장할 수 없습니다.")
    if len(text) > MAX_RULE_LENGTH:
        raise RuleError(f"규칙은 {MAX_RULE_LENGTH}자를 넘을 수 없습니다.")
    m = RULE_FORM.match(text)
    if m is None:
        raise RuleError(f"규칙 형식이 올바르지 않습니다: {text[:60]}")
    tool, body = m.group(1), m.group(2)
    if tool == "Bash":
        return _parse_shell(body)
    if tool in ("Read", "Edit", "Write"):
        return _parse_glob(tool, body)
    if tool in PLAIN_TOOLS:
        if body is not None:
            raise RuleError(f"`{tool}` 규칙은 괄호 없이 이름만 쓸 수 있습니다.")
        return Rule("tool", tool, tool)
    if tool.startswith("mcp__"):
        if tool.startswith("mcp__org__"):
            raise RuleError("위임 도구(mcp__org__*)는 허용 규칙에 넣을 수 없습니다.")
        if body is not None or MCP_TOOL.match(tool) is None:
            raise RuleError("MCP 규칙은 `mcp__서버__도구` 형태로 도구 하나만 지정할 수 있습니다.")
        return Rule("tool", tool, tool)
    raise RuleError(
        f"지원하지 않는 도구입니다: {tool[:40]} "
        "(Bash·Read·Edit·Write·WebSearch·WebFetch·mcp__서버__도구만 가능)"
    )


def normalize(raw_rules: list[str]) -> list[str]:
    """규칙 목록을 검증하고 정리된 형태로 돌려준다(중복 제거, 순서 유지)."""
    out: list[str] = []
    for raw in raw_rules:
        text = parse(raw).text
        if text not in out:
            out.append(text)
    if len(out) > MAX_RULES:
        raise RuleError(f"허용 규칙은 에이전트당 {MAX_RULES}개까지 저장할 수 있습니다.")
    return out


def keep_valid(raw_rules: Any) -> tuple[list[str], list[str]]:
    """저장돼 있던 규칙 중 지금 검증을 통과하는 것만 남긴다. (남긴 규칙, 버린 규칙).

    검증이 강화된 뒤에도 실행이 깨지지 않게 하려는 것이다. 버리는 쪽은 항상 '더 묻는' 쪽이다.
    """
    kept: list[str] = []
    dropped: list[str] = []
    for raw in raw_rules if isinstance(raw_rules, list) else []:
        try:
            text = parse(raw).text
        except RuleError:
            dropped.append(str(raw)[:MAX_RULE_LENGTH])
            continue
        if text not in kept:
            kept.append(text)
    return kept[:MAX_RULES], dropped + kept[MAX_RULES:]


# ── 매칭 ───────────────────────────────────────────────────────────────────


def split_command(command: str) -> list[str] | None:
    """복합 명령을 조각으로 나눈다. 규칙과 대조할 수 없는 명령이면 None.

    따옴표를 해석하지 않고 연결 기호마다 나눈다. 셸이 실제로 나누는 것보다 잘게 나뉠 수 있지만
    조각이 **모두** 규칙에 맞아야 하므로 틀려도 '묻는' 쪽으로만 틀린다.
    """
    if any(token in command for token in COMMAND_OPAQUE):
        return None
    if is_delete(command):
        return None
    segments = [s.strip() for s in SEGMENT_SPLIT.split(command)]
    if not segments or any(not s for s in segments):
        return None
    return segments


def _segment_rule(segment: str, shell_rules: list[Rule]) -> Rule | None:
    words = _words(segment)
    if not words or ASSIGNMENT.match(words[0]) or unsafe(segment) is not None:
        return None
    flat = " ".join(segment.split())
    for rule in shell_rules:
        if flat == rule.pattern:
            return rule
        if rule.kind == "shell_prefix" and flat.startswith(rule.pattern + " "):
            return rule
    return None


def _match_shell(command: str, parsed: list[Rule]) -> str | None:
    shell_rules = [r for r in parsed if r.kind in ("shell_prefix", "shell_exact")]
    if not shell_rules:
        return None
    segments = split_command(command)
    if segments is None:
        return None
    matched = [_segment_rule(s, shell_rules) for s in segments]
    if any(rule is None for rule in matched):
        return None
    if len(segments) > 1:
        return "허용 규칙(복합 명령의 모든 조각 일치)"
    return matched[0].text if matched[0] is not None else None


def glob_regex(glob: str) -> re.Pattern[str]:
    """글롭을 정규식으로 바꾼다(Python 3.12에는 PurePath.full_match가 없다).

    `**`는 여러 폴더, `*`·`?`는 한 경로 조각 안에서만 일치한다. `폴더/**`는 그 폴더 자신도 포함한다.
    """
    out: list[str] = []
    i, n = 0, len(glob)
    while i < n:
        if glob.startswith("**/", i) and (i == 0 or glob[i - 1] == "/"):
            out.append("(?:.*/)?")
            i += 3
        elif glob.startswith("/**", i) and i + 3 == n:
            out.append("(?:/.*)?")
            i += 3
        elif glob.startswith("**", i):
            out.append(".*")
            i += 2
        elif glob[i] == "*":
            out.append("[^/]*")
            i += 1
        elif glob[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(glob[i]))
            i += 1
    return re.compile("".join(out), re.S)


# ── 파일 도구의 경로성 인자 ────────────────────────────────────────────────

GLOB_CHARS = ("*", "?", "[", "{")
# 중괄호 확장 안에 절대 경로·홈·상위 폴더가 들어 있는 형태(`{/etc,x}`, `{..,x}`).
BRACE_ESCAPE = re.compile(r"[{,]\s*(/|~|\.\.)")


def _within(path: Path, roots: list[Path]) -> bool:
    return any(path == root or root in path.parents for root in roots)


def glob_escapes(pattern: str, base: Path, roots: list[Path]) -> bool:
    """글롭(Glob의 pattern, Grep의 glob)이 허용 범위 밖을 가리킬 수 있는가.

    글롭 문자가 없는 앞부분을 실제 경로로 풀어 범위를 확인한다. 그 뒤에 `..`이나 `..`으로 풀릴 수 있는
    조각(`.{.,}`, `.?`, `.*`)이 있으면 범위 밖일 수 있다고 본다.
    """
    if BRACE_ESCAPE.search(pattern):
        return True
    segments = pattern.split("/")
    static: list[str] = []
    for segment in segments:
        if any(ch in segment for ch in GLOB_CHARS):
            break
        static.append(segment)
    for segment in segments[len(static) :]:
        if segment == "..":
            return True
        if segment.startswith(".") and any(ch in segment for ch in GLOB_CHARS):
            return True
    prefix = Path("/".join(static) or ".").expanduser()
    resolved = prefix.resolve() if prefix.is_absolute() else (base / prefix).resolve()
    return not _within(resolved, roots)


def file_outside(tool: str, tool_input: dict[str, Any], roots: list[Path]) -> bool:
    """도구 입력의 경로성 인자 중 허용 범위(roots) 밖을 가리키는 것이 있는가.

    file_path·notebook_path·path는 심볼릭 링크를 해석한 실제 경로로, Glob의 pattern과 Grep의 glob은
    glob_escapes로 본다(Grep의 pattern은 정규식이라 경로로 보지 않는다).
    """
    if not roots:
        return False
    base = roots[0]
    for key in PATH_KEYS:
        raw = tool_input.get(key)
        if isinstance(raw, str) and raw:
            target = Path(raw).expanduser()
            resolved = target.resolve() if target.is_absolute() else (roots[0] / target).resolve()
            if not _within(resolved, roots):
                return True
            if key == "path":
                base = resolved
    globs = [tool_input.get("glob")]
    if tool == "Glob":
        globs.append(tool_input.get("pattern"))
    return any(isinstance(g, str) and bool(g) and glob_escapes(g, base, roots) for g in globs)


def relative_target(tool_input: dict[str, Any], roots: list[Path], tool: str = "") -> str | None:
    """도구 입력의 경로를 작업 폴더(roots[0]) 기준 상대 경로로 돌려준다.

    심볼릭 링크를 해석한 실제 경로가 작업 폴더 밖(첨부 폴더 포함)이면 None. Glob의 pattern·Grep의 glob이
    작업 폴더 밖을 가리킬 수 있어도 None. 경로 입력이 없으면 작업 폴더 전체를 뜻하는 빈 문자열.
    """
    if not roots:
        return None
    root = roots[0].resolve()
    if file_outside(tool, tool_input, [root]):
        return None
    raw = next((v for k in PATH_KEYS if isinstance(v := tool_input.get(k), str) and v), None)
    if raw is None:
        return ""
    target = Path(raw).expanduser()
    resolved = target.resolve() if target.is_absolute() else (root / target).resolve()
    if resolved == root:
        return ""
    if root not in resolved.parents:
        return None
    return resolved.relative_to(root).as_posix()


def match(rules: list[str], tool: str, tool_input: dict[str, Any], roots: list[Path]) -> str | None:
    """도구 호출이 허용 리스트에 맞으면 맞은 규칙(설명용 문자열), 아니면 None.

    작업 폴더 밖 판정은 호출하는 쪽(policy.decide)이 먼저 한다. 여기서도 파일 경로는 다시 확인한다.
    """
    parsed: list[Rule] = []
    for raw in rules:
        try:
            parsed.append(parse(raw))
        except RuleError:
            continue  # 저장된 뒤 기준이 엄격해진 규칙은 무시한다(= 묻는다).
    if not parsed:
        return None
    if tool == "Bash":
        command = tool_input.get("command")
        return _match_shell(command, parsed) if isinstance(command, str) and command.strip() else None
    if tool in READ_RULE_TOOLS or tool in WRITE_RULE_TOOLS:
        kind = "read" if tool in READ_RULE_TOOLS else "write"
        rel = relative_target(tool_input, roots, tool)
        if rel is None:
            return None
        for rule in parsed:
            if rule.kind == kind and glob_regex(rule.pattern).fullmatch(rel):
                return rule.text
        return None
    for rule in parsed:
        if rule.kind == "tool" and rule.pattern == tool:
            return rule.text
    return None


# ── '항상 허용' 규칙 생성 ───────────────────────────────────────────────────


def _shell_candidate(words: list[str], flat: str) -> str:
    """'항상 허용'으로 만들 셸 규칙. flat은 공백을 정리한 명령 전체.

    기본은 명령 전체 일치다. 접두 규칙은 하위 명령 도구의 두 단어(`git status`, `npm test`)와
    스크립트 실행 세 단어(`npm run test`)만 만든다. 대리 실행(`uv run …`)·인터프리터는 전체 일치.
    """
    exact = f"Bash({flat})"
    name = _name(words[0])
    if name not in SUBCOMMAND_TOOLS or name in PACKAGE_RUNNERS:
        return exact  # npx·bunx·pipx는 실행할 패키지·인자가 고정돼야 한다.

    def plain(index: int) -> bool:
        return (
            len(words) > index and not words[index].startswith("-") and bool(PLAIN_WORD.match(words[index]))
        )

    if not plain(1) or _prefix_problem(words[:2]) is not None:
        if plain(1) and words[1] == "run" and name in SCRIPT_RUNNERS and plain(2):
            return f"Bash({words[0]} run {words[2]}:*)"
        return exact
    return f"Bash({words[0]} {words[1]}:*)"


def suggest(
    tool: str,
    tool_input: dict[str, Any],
    roots: list[Path],
    *,
    group: str | None = None,
    outside: bool = False,
) -> tuple[str | None, str]:
    """이 요청을 '항상 허용'할 때 추가할 규칙. 만들 수 없으면 (None, 사유)."""
    if group == "delegate" or tool in ("Agent", "Task") or tool.startswith("mcp__org__"):
        return None, "위임 요청은 항상 허용할 수 없습니다."
    if group == "file_delete":
        return None, "삭제 요청은 항상 허용할 수 없습니다."
    if outside:
        return None, "작업 폴더 밖 경로를 참조하는 요청은 항상 허용할 수 없습니다."
    if tool == "Bash":
        command = tool_input.get("command")
        if not isinstance(command, str) or not command.strip():
            return None, "명령이 없어 규칙을 만들 수 없습니다."
        segments = split_command(command)
        if segments is None or len(segments) != 1:
            return None, "복합 명령·명령 치환·리다이렉션이 있는 명령은 항상 허용할 수 없습니다."
        words = _words(segments[0])
        if not words or ASSIGNMENT.match(words[0]):
            return None, "`변수=값`으로 시작하는 명령은 항상 허용할 수 없습니다."
        if (reason := unsafe(segments[0])) is not None:
            return None, reason
        if re.fullmatch(r"[A-Za-z0-9_./+-]+", words[0]) is None:
            return None, "명령 이름을 알 수 없어 규칙을 만들 수 없습니다."
        candidate = _shell_candidate(words, " ".join(segments[0].split()))
    elif tool in READ_RULE_TOOLS or tool in WRITE_RULE_TOOLS:
        rel = relative_target(tool_input, roots, tool)
        if rel is None:
            return None, "작업 폴더 밖 경로는 항상 허용할 수 없습니다."
        if not rel:
            # 경로 없는 Grep·Glob 등: 작업 폴더 전체(`Read(**)`)를 자동으로 열지 않는다.
            return None, "경로를 지정하지 않은(작업 폴더 전체) 요청은 항상 허용할 수 없습니다."
        if any(ch in rel for ch in "*?"):
            return None, "경로에 `*`·`?`가 있어 규칙을 만들 수 없습니다."
        name = "Read" if tool in READ_RULE_TOOLS else "Edit"
        candidate = f"{name}({rel})"
    elif tool in PLAIN_TOOLS or tool.startswith("mcp__"):
        candidate = tool
    else:
        return None, f"`{tool}` 도구는 허용 규칙으로 만들 수 없습니다."
    try:
        return parse(candidate).text, ""
    except RuleError as exc:
        return None, str(exc)
