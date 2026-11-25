"""로컬 프로젝트 탐색과 Git 정보(읽기 전용).

- 경로는 항상 resolve()한 실제 경로로 다룬다(심볼릭 링크로 등록 범위를 벗어나지 않게).
- 탐색은 등록된 루트 아래로만, 깊이 제한을 둔다. 숨김 디렉터리와 의존성 폴더는 건너뛴다.
- Git은 `git` CLI를 인자 배열로 호출하고(셸 없음) 짧은 타임아웃을 둔다. 저장소를 바꾸는 명령은 쓰지 않는다.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from ai_org.schemas import GitInfo

SKIP_DIRS = {"node_modules", ".venv", "venv", "__pycache__", "dist", "build", "target", ".git"}
MARKERS: tuple[tuple[str, str], ...] = (
    ("package.json", "node"),
    ("pyproject.toml", "python"),
    ("requirements.txt", "python"),
    ("go.mod", "go"),
    ("Cargo.toml", "rust"),
    ("pom.xml", "java"),
    ("build.gradle", "java"),
    ("Gemfile", "ruby"),
    ("CMakeLists.txt", "cpp"),
)
GIT_TIMEOUT = 5


class PathNotAllowed(ValueError):
    pass


def resolve_dir(raw: str) -> Path:
    path = Path(raw).expanduser()
    if not path.is_absolute():
        raise PathNotAllowed("absolute path required")
    resolved = path.resolve()
    if not resolved.is_dir():
        raise PathNotAllowed("directory does not exist")
    return resolved


def is_within(path: Path, roots: list[Path]) -> bool:
    return any(path == root or root in path.parents for root in roots)


def detect_kind(path: Path) -> str:
    kinds = [kind for marker, kind in MARKERS if (path / marker).exists()]
    if not kinds:
        return "unknown"
    return kinds[0] if len(set(kinds)) == 1 else "mixed"


def looks_like_project(path: Path) -> bool:
    return (path / ".git").exists() or any((path / marker).exists() for marker, _ in MARKERS)


def scan(root: Path, max_depth: int) -> list[Path]:
    """root 아래 프로젝트로 보이는 디렉터리. 프로젝트 안으로는 더 내려가지 않는다."""
    found: list[Path] = []

    def walk(path: Path, depth: int) -> None:
        if looks_like_project(path):
            found.append(path)
            return
        if depth >= max_depth:
            return
        try:
            children = sorted(p for p in path.iterdir() if p.is_dir() and not p.is_symlink())
        except OSError:
            return
        for child in children:
            if child.name.startswith(".") or child.name in SKIP_DIRS:
                continue
            walk(child, depth + 1)

    walk(root, 0)
    return found


def _git(path: Path, *args: str) -> str | None:
    try:
        out = subprocess.run(
            ["git", "-C", str(path), *args],
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT,
            check=False,
            env={"GIT_OPTIONAL_LOCKS": "0", "LC_ALL": "C", "PATH": "/usr/bin:/bin:/usr/local/bin"},
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return out.stdout.strip() if out.returncode == 0 else None


def git_info(path: Path) -> GitInfo:
    if _git(path, "rev-parse", "--is-inside-work-tree") != "true":
        return GitInfo(is_repo=False)
    branch = _git(path, "symbolic-ref", "--short", "-q", "HEAD")
    head = _git(path, "rev-parse", "--short", "HEAD")
    subject = _git(path, "log", "-1", "--format=%s") if head else None
    status = _git(path, "status", "--porcelain") or ""
    remote = _git(path, "remote", "get-url", "origin")
    ahead = behind = None
    counts = _git(path, "rev-list", "--left-right", "--count", "HEAD...@{upstream}")
    if counts:
        left, _, right = counts.partition("\t")
        if left.isdigit() and right.isdigit():
            ahead, behind = int(left), int(right)
    if remote and "@" in remote and remote.startswith("http"):
        # 자격증명이 URL에 들어 있으면 지운다.
        scheme, _, rest = remote.partition("://")
        remote = f"{scheme}://{rest.split('@', 1)[1]}"
    return GitInfo(
        is_repo=True,
        branch=branch,
        head=head,
        head_subject=subject,
        dirty_files=len([line for line in status.splitlines() if line.strip()]),
        ahead=ahead,
        behind=behind,
        remote=remote,
    )
