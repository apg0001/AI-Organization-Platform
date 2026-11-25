"""데스크톱 앱(트레이·네이티브 알림)용 요약 API.

데스크톱 앱이 백엔드를 띄울 때 넘긴 토큰(`AI_ORG_DESKTOP_TOKEN`)으로만 접근한다(AuthMiddleware가 검사).
토큰이 없으면(브라우저 실행) 이 경로는 404다.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Request
from sqlalchemy import func, select

from ai_org import __version__
from ai_org.models import Approval

router = APIRouter(prefix="/api/v1/desktop", tags=["desktop"])


@router.get("/summary")
def summary(request: Request, after: int = Query(0, ge=0)) -> dict[str, Any]:
    app = request.app
    with app.state.session_factory() as db:
        pending = select(func.count()).select_from(Approval).where(Approval.status == "pending")
        approvals = db.scalar(pending) or 0
    usage = [
        {"provider": r.name, "label": w.label, "percent": round(w.percent, 1)}
        for r in app.state.usage.last.values()
        if r.state == "ok"
        for w in r.windows
    ]
    notifier = app.state.notifier
    return {
        "version": __version__,
        "running": len(app.state.runs.runs),
        "approvals": approvals,
        "usage": usage,
        "notifications": notifier.since(after),
        "latest_id": notifier.seq,
    }
