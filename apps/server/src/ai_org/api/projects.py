"""로컬 프로젝트 API. 등록된 루트 아래 경로만 프로젝트로 등록할 수 있다."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Response
from sqlalchemy import select

from ai_org.deps import DB, not_found
from ai_org.models import ActivityEvent, Organization, Project, ProjectRoot
from ai_org.schemas import (
    GitInfo,
    ProjectCandidate,
    ProjectDetail,
    ProjectIn,
    ProjectOut,
    ProjectPatch,
    ProjectRootIn,
    ProjectRootOut,
)
from ai_org.services import projects as svc

router = APIRouter(prefix="/api/v1", tags=["projects"])


def _roots(db: DB) -> list[ProjectRoot]:
    return list(db.scalars(select(ProjectRoot).order_by(ProjectRoot.created_at)))


def _out(project: Project) -> ProjectOut:
    return ProjectOut.model_validate(project).model_copy(update={"exists": Path(project.path).is_dir()})


@router.get("/project-roots", response_model=list[ProjectRootOut])
def list_roots(db: DB) -> list[ProjectRootOut]:
    return [
        ProjectRootOut.model_validate(root).model_copy(update={"exists": Path(root.path).is_dir()})
        for root in _roots(db)
    ]


@router.post("/project-roots", response_model=ProjectRootOut, status_code=201)
def add_root(body: ProjectRootIn, db: DB) -> ProjectRoot:
    try:
        path = svc.resolve_dir(body.path)
    except svc.PathNotAllowed as exc:
        raise HTTPException(422, str(exc)) from exc
    if path == Path(path.anchor):
        raise HTTPException(422, "registering the filesystem root is not allowed")
    if db.scalar(select(ProjectRoot).where(ProjectRoot.path == str(path))) is not None:
        raise HTTPException(409, "root already registered")
    root = ProjectRoot(path=str(path), max_depth=body.max_depth)
    db.add(root)
    db.add(ActivityEvent(kind="project_root.added", summary=f"탐색 경로 등록: {path}"))
    db.commit()
    return root


@router.delete("/project-roots/{root_id}", status_code=204)
def remove_root(root_id: str, db: DB) -> Response:
    root = db.get(ProjectRoot, root_id)
    if root is None:
        raise not_found("root")
    db.delete(root)
    db.commit()
    return Response(status_code=204)


@router.get("/project-roots/scan", response_model=list[ProjectCandidate])
def scan_roots(db: DB) -> list[ProjectCandidate]:
    registered = set(db.scalars(select(Project.path)))
    out: list[ProjectCandidate] = []
    seen: set[str] = set()
    for root in _roots(db):
        root_path = Path(root.path)
        if not root_path.is_dir():
            continue
        for path in svc.scan(root_path, root.max_depth):
            if str(path) in seen:
                continue
            seen.add(str(path))
            out.append(
                ProjectCandidate(
                    name=path.name,
                    path=str(path),
                    kind=svc.detect_kind(path),
                    is_git=(path / ".git").exists(),
                    registered=str(path) in registered,
                )
            )
    return out


@router.get("/projects", response_model=list[ProjectOut])
def list_projects(db: DB) -> list[ProjectOut]:
    return [_out(p) for p in db.scalars(select(Project).order_by(Project.name))]


@router.post("/projects", response_model=ProjectOut, status_code=201)
def add_project(body: ProjectIn, db: DB) -> ProjectOut:
    try:
        path = svc.resolve_dir(body.path)
    except svc.PathNotAllowed as exc:
        raise HTTPException(422, str(exc)) from exc
    roots = [Path(r.path) for r in _roots(db)]
    if not svc.is_within(path, roots):
        raise HTTPException(403, "path is outside registered project roots")
    if db.scalar(select(Project).where(Project.path == str(path))) is not None:
        raise HTTPException(409, "project already registered")
    if body.organization_id and db.get(Organization, body.organization_id) is None:
        raise not_found("organization")
    project = Project(
        name=body.name or path.name,
        path=str(path),
        description=body.description,
        kind=svc.detect_kind(path),
        organization_id=body.organization_id,
    )
    db.add(project)
    db.add(
        ActivityEvent(
            organization_id=body.organization_id,
            kind="project.added",
            summary=f"프로젝트 '{project.name}' 등록",
        )
    )
    db.commit()
    return _out(project)


@router.get("/projects/{project_id}", response_model=ProjectDetail)
def get_project(project_id: str, db: DB) -> ProjectDetail:
    project = db.get(Project, project_id)
    if project is None:
        raise not_found("project")
    path = Path(project.path)
    git = svc.git_info(path) if path.is_dir() else GitInfo(is_repo=False, error="path missing")
    return ProjectDetail(**_out(project).model_dump(), git=git)


@router.get("/projects/{project_id}/tree")
def project_tree(project_id: str, db: DB, path: str = "") -> dict[str, object]:
    """프로젝트 안 디렉터리 한 단계 목록(컨텍스트 선택용). 프로젝트 밖으로 나갈 수 없다."""
    project = db.get(Project, project_id)
    if project is None:
        raise not_found("project")
    root = Path(project.path).resolve()
    target = (root / path).resolve()
    if not svc.is_within(target, [root]) or not target.is_dir():
        raise HTTPException(403, "path is outside the project")
    entries = []
    try:
        children = sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    except OSError as exc:
        raise HTTPException(403, "cannot read directory") from exc
    for child in children[:500]:
        if child.name in svc.SKIP_DIRS or child.name.startswith(".git"):
            continue
        if child.is_symlink():
            continue
        entries.append(
            {
                "name": child.name,
                "path": str(child.relative_to(root)),
                "is_dir": child.is_dir(),
            }
        )
    return {"path": str(target.relative_to(root)) if target != root else "", "entries": entries}


@router.patch("/projects/{project_id}", response_model=ProjectOut)
def update_project(project_id: str, body: ProjectPatch, db: DB) -> ProjectOut:
    project = db.get(Project, project_id)
    if project is None:
        raise not_found("project")
    data = body.model_dump(exclude_unset=True)
    if data.get("organization_id") and db.get(Organization, data["organization_id"]) is None:
        raise not_found("organization")
    for key, value in data.items():
        setattr(project, key, value)
    db.commit()
    return _out(project)


@router.delete("/projects/{project_id}", status_code=204)
def remove_project(project_id: str, db: DB) -> Response:
    """레지스트리에서만 제거한다. 디스크의 파일은 건드리지 않는다."""
    project = db.get(Project, project_id)
    if project is None:
        raise not_found("project")
    db.delete(project)
    db.commit()
    return Response(status_code=204)
