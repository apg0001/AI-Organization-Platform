"""Capability 탐색(읽기 전용).

Claude Code 설정 파일을 읽어 Skills·MCP 서버·Plugins 목록을 만든다. 쓰지 않는다.
비밀이 들어 있을 수 있는 값(env, headers, args, url의 쿼리)은 응답에 절대 넣지 않는다.

출처:
- Skills: ~/.claude/skills/*/SKILL.md (user), <project>/.claude/skills/*/SKILL.md (project)
- MCP: ~/.claude.json 의 mcpServers(user) 및 projects[<path>].mcpServers(local), <project>/.mcp.json(project)
- Plugins: ~/.claude/plugins/installed_plugins.json
연결 상태 점검(health check)은 Phase 4에서 `claude mcp list` 등 공식 경로로 수행한다.
"""

from __future__ import annotations

import json
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
