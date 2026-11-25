"""Capability 탐색(읽기 전용).

Claude Code 설정 파일을 읽어 Skills·MCP 서버·Plugins 목록을 만든다. 쓰지 않는다.
비밀이 들어 있을 수 있는 값(env, headers, args, url의 쿼리)은 응답에 절대 넣지 않는다.

출처:
- Skills: ~/.claude/skills/*/SKILL.md (user), <project>/.claude/skills/*/SKILL.md (project)
- MCP: ~/.claude.json 의 mcpServers(user) 및 projects[<path>].mcpServers(local), <project>/.mcp.json(project)
- Plugins: ~/.claude/plugins/installed_plugins.json
실행 연결: `resolve_mcp_servers`/`resolve_plugin_paths`가 에이전트에게 허용된 항목의 원본 설정을
서버 안에서만 꺼낸다(비밀 값 포함 — API 응답·DB에 넣지 않고 실행 옵션으로만 전달).
연결 상태 점검은 `claude mcp list`(`mcp_health`).
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import yaml

MAX_FILE_BYTES = 2_000_000


@dataclass
class Capability:
    id: str  # "skill:user:frontend-design", "mcp:user:github", "plugin:foo@market"
    kind: str  # skill | mcp | plugin
    name: str
    scope: str  # user | project | local | plugin
    description: str = ""
    source: str = ""  # 사람이 읽는 출처(경로 등, 홈은 ~로 줄임)
    transport: str | None = None  # mcp: stdio | http | sse
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _tilde(path: Path) -> str:
    try:
        return "~/" + str(path.relative_to(Path.home()))
    except ValueError:
        return str(path)


def _read_json(path: Path) -> Any:
    if not path.is_file() or path.stat().st_size > MAX_FILE_BYTES:
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _frontmatter(text: str) -> dict[str, Any]:
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    try:
        data = yaml.safe_load(text[3:end])
    except yaml.YAMLError:
        return {}
    return data if isinstance(data, dict) else {}


def discover_skills(base: Path, scope: str) -> list[Capability]:
    skills_dir = base / "skills"
    if not skills_dir.is_dir():
        return []
    found: list[Capability] = []
    for entry in sorted(skills_dir.iterdir()):
        skill_md = entry / "SKILL.md"
        if not skill_md.is_file() or skill_md.stat().st_size > MAX_FILE_BYTES:
            continue
        meta = _frontmatter(skill_md.read_text(encoding="utf-8", errors="replace"))
        name = str(meta.get("name") or entry.name)
        found.append(
            Capability(
                id=f"skill:{scope}:{name}",
                kind="skill",
                name=name,
                scope=scope,
                description=str(meta.get("description") or "").strip(),
                source=_tilde(entry),
            )
        )
    return found


def _safe_mcp(name: str, raw: Any, scope: str, source: str) -> Capability:
    """MCP 설정에서 비밀이 아닌 값만 남긴다."""
    cfg = raw if isinstance(raw, dict) else {}
    transport = str(cfg.get("type") or ("stdio" if "command" in cfg else "http"))
    detail: dict[str, Any] = {}
    if transport == "stdio" and isinstance(cfg.get("command"), str):
        # 명령 이름만(경로·인자는 토큰이 들어갈 수 있어 제외).
        detail["command"] = Path(cfg["command"]).name
    url = cfg.get("url")
    if isinstance(url, str):
        parts = urlsplit(url)
        detail["host"] = parts.hostname or ""
    if isinstance(cfg.get("env"), dict):
        detail["env_keys"] = len(cfg["env"])
    if isinstance(cfg.get("headers"), dict):
        detail["header_keys"] = len(cfg["headers"])
    return Capability(
        id=f"mcp:{scope}:{name}",
        kind="mcp",
        name=name,
        scope=scope,
        transport=transport,
        source=source,
        detail=detail,
    )


def discover_mcp(claude_json: Path, project_paths: list[str]) -> list[Capability]:
    data = _read_json(claude_json)
    found: list[Capability] = []
    if isinstance(data, dict):
        for name, cfg in sorted((data.get("mcpServers") or {}).items()):
            found.append(_safe_mcp(name, cfg, "user", _tilde(claude_json)))
        projects = data.get("projects") or {}
        for path in project_paths:
            entry = projects.get(path) if isinstance(projects, dict) else None
            if isinstance(entry, dict):
                for name, cfg in sorted((entry.get("mcpServers") or {}).items()):
                    found.append(_safe_mcp(name, cfg, "local", f"{_tilde(claude_json)} · {Path(path).name}"))
    for path in project_paths:
        mcp_json = Path(path) / ".mcp.json"
        project_data = _read_json(mcp_json)
        if isinstance(project_data, dict):
            for name, cfg in sorted((project_data.get("mcpServers") or {}).items()):
                found.append(_safe_mcp(name, cfg, "project", _tilde(mcp_json)))
    return found


def discover_plugins(claude_home: Path) -> list[Capability]:
    data = _read_json(claude_home / "plugins" / "installed_plugins.json")
    if not isinstance(data, dict):
        return []
    plugins = data.get("plugins", data)
    found: list[Capability] = []
    if not isinstance(plugins, dict):
        return found
    for key, value in sorted(plugins.items()):
        installs = value if isinstance(value, list) else [value]
        first = installs[0] if installs and isinstance(installs[0], dict) else {}
        install_path = first.get("installPath")
        description = ""
        if isinstance(install_path, str):
            manifest = _read_json(Path(install_path) / ".claude-plugin" / "plugin.json")
            if isinstance(manifest, dict):
                description = str(manifest.get("description") or "")
        name, _, marketplace = key.partition("@")
        found.append(
            Capability(
                id=f"plugin:{key}",
                kind="plugin",
                name=name,
                scope="plugin",
                description=description,
                source=marketplace or "",
                detail={"version": first.get("version"), "installs": len(installs)},
            )
        )
    return found


def discover_all(claude_home: Path, project_paths: list[str]) -> list[Capability]:
    claude_json = (
        claude_home.parent / ".claude.json" if claude_home.name == ".claude" else claude_home / ".claude.json"
    )
    caps: list[Capability] = []
    caps += discover_skills(claude_home, "user")
    for path in project_paths:
        caps += [
            Capability(
                **{**c.to_dict(), "id": f"skill:project:{Path(path).name}:{c.name}", "scope": "project"}
            )
            for c in discover_skills(Path(path) / ".claude", "project")
        ]
    caps += discover_mcp(claude_json, project_paths)
    caps += discover_plugins(claude_home)
    return caps


# ── 실행 연결(서버 내부 전용) ──────────────────────────────────────────────


def _claude_json(claude_home: Path) -> Path:
    return (
        claude_home.parent / ".claude.json" if claude_home.name == ".claude" else claude_home / ".claude.json"
    )


def resolve_mcp_servers(
    claude_home: Path, project_paths: list[str], allowed_ids: list[str]
) -> dict[str, Any]:
    """허용된 MCP 서버 ID(mcp:<scope>:<name>)의 원본 설정. 비밀이 들어 있으므로 실행 옵션으로만 쓴다."""
    wanted = {
        cid.split(":", 2)[2]: cid.split(":", 2)[1]
        for cid in allowed_ids
        if cid.startswith("mcp:") and cid.count(":") >= 2
    }
    if not wanted:
        return {}
    sources: list[tuple[str, dict[str, Any]]] = []
    data = _read_json(_claude_json(claude_home))
    if isinstance(data, dict):
        sources.append(("user", data.get("mcpServers") or {}))
        projects = data.get("projects") or {}
        for path in project_paths:
            entry = projects.get(path) if isinstance(projects, dict) else None
            if isinstance(entry, dict):
                sources.append(("local", entry.get("mcpServers") or {}))
    for path in project_paths:
        project_data = _read_json(Path(path) / ".mcp.json")
        if isinstance(project_data, dict):
            sources.append(("project", project_data.get("mcpServers") or {}))
    resolved: dict[str, Any] = {}
    for scope, servers in sources:
        if not isinstance(servers, dict):
            continue
        for name, cfg in servers.items():
            if wanted.get(name) == scope and name not in resolved and isinstance(cfg, dict):
                resolved[name] = dict(cfg)
    return resolved


def resolve_plugin_paths(claude_home: Path, allowed_ids: list[str]) -> list[str]:
    data = _read_json(claude_home / "plugins" / "installed_plugins.json")
    if not isinstance(data, dict):
        return []
    plugins = data.get("plugins", data)
    paths: list[str] = []
    for cid in allowed_ids:
        key = cid.removeprefix("plugin:")
        value = plugins.get(key) if isinstance(plugins, dict) else None
        installs = value if isinstance(value, list) else [value]
        first = installs[0] if installs and isinstance(installs[0], dict) else {}
        install_path = first.get("installPath")
        if isinstance(install_path, str) and Path(install_path).is_dir():
            paths.append(install_path)
    return paths


HEALTH_LINE = re.compile(r"^(?P<name>[^:]+): (?P<target>.*) - (?P<symbol>\S+) (?P<text>.+)$")
HEALTH_STATES = (
    ("Connected", "connected"),
    ("Needs authentication", "needs_auth"),
    ("Failed", "failed"),
    ("Pending approval", "pending_approval"),
    ("Rejected", "disabled"),
    ("Disabled", "disabled"),
    ("Blocked", "disabled"),
)


def parse_mcp_list(output: str) -> list[dict[str, str]]:
    found = []
    for line in output.splitlines():
        m = HEALTH_LINE.match(line.strip())
        if not m:
            continue
        text = m.group("text").strip()
        state = next((s for key, s in HEALTH_STATES if text.startswith(key)), "unknown")
        found.append({"name": m.group("name").strip(), "state": state, "message": text})
    return found


def mcp_health(claude_bin: str, cwd: Path, timeout: float = 120) -> list[dict[str, str]]:
    """`claude mcp list`로 서버 연결 상태를 점검한다(서버를 실제로 띄워 보므로 시간이 걸린다)."""
    try:
        out = subprocess.run(
            [claude_bin, "mcp", "list"], cwd=cwd, capture_output=True, text=True, timeout=timeout, check=False
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return [{"name": "*", "state": "error", "message": str(exc)[:200]}]
    return parse_mcp_list(out.stdout)
