"""시스템·워크스페이스·Capability(읽기 전용) API."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter
from sqlalchemy import select

from ai_org import __version__
from ai_org.api.organizations import list_organizations
from ai_org.deps import DB, AppSettings
from ai_org.models import ActivityEvent, Agent, Approval, Project, Task
from ai_org.runtime.claude_code import ClaudeCodeRuntime
from ai_org.schemas import (
    ActivityOut,
    AgentOut,
    ApprovalOut,
    ProjectOut,
    SystemInfo,
    TaskOut,
    WorkspaceOverview,
)
from ai_org.services.capabilities import discover_all

router = APIRouter(prefix="/api/v1", tags=["system"])

ACTIVE_STATUSES = ("thinking", "working", "waiting", "reviewing")


@router.get("/system/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/system/info", response_model=SystemInfo)
def system_info(settings: AppSettings) -> SystemInfo:
    return SystemInfo(
        version=__version__,
        data_dir=str(settings.home),
        runtimes=[ClaudeCodeRuntime(settings.claude_bin).detect()],
    )


@router.get("/workspace", response_model=WorkspaceOverview)
def workspace(db: DB) -> WorkspaceOverview:
    return WorkspaceOverview(
        organizations=list_organizations(db),
        projects=[ProjectOut.model_validate(p) for p in db.scalars(select(Project).order_by(Project.name))],
        running_agents=[
            AgentOut.model_validate(a)
            for a in db.scalars(select(Agent).where(Agent.status.in_(ACTIVE_STATUSES)))
        ],
        recent_tasks=[
            TaskOut.model_validate(t)
            for t in db.scalars(select(Task).order_by(Task.updated_at.desc()).limit(10))
        ],
        pending_approvals=[
            ApprovalOut.model_validate(a)
            for a in db.scalars(
                select(Approval).where(Approval.status == "pending").order_by(Approval.created_at)
            )
        ],
        activity=[
            ActivityOut.model_validate(e)
            for e in db.scalars(select(ActivityEvent).order_by(ActivityEvent.created_at.desc()).limit(20))
        ],
    )


@router.get("/capabilities/mcp/health")
async def capabilities_mcp_health(db: DB, settings: AppSettings) -> list[dict[str, str]]:
    """MCP 연결 점검(`claude mcp list`): 사용자 범위는 홈, 프로젝트 범위는 등록 프로젝트에서."""
    import asyncio

    from ai_org.services.capabilities import mcp_health

    folders = [Path.home()] + [
        Path(p) for p in db.scalars(select(Project.path)) if (Path(p) / ".mcp.json").is_file()
    ]
    results = await asyncio.gather(*(asyncio.to_thread(mcp_health, settings.claude_bin, f) for f in folders))
    merged: dict[str, dict[str, str]] = {}
    for rows in results:
        for row in rows:
            merged.setdefault(row["name"], row)
    return list(merged.values())


@router.get("/capabilities")
def capabilities(db: DB, settings: AppSettings) -> list[dict[str, Any]]:
    project_paths = list(db.scalars(select(Project.path)))
    return [c.to_dict() for c in discover_all(settings.claude_home, project_paths)]
