"""AI 사용량 API. 조회 결과에는 사용률·초기화 시각·예측만 있고 토큰·계정 정보는 없다."""

from __future__ import annotations

import asyncio
import contextlib
from pathlib import Path
from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from ai_org.deps import DB
from ai_org.models import ActivityEvent
from ai_org.services import usage as svc

router = APIRouter(prefix="/api/v1/usage", tags=["usage"])


class UsageSettingsIn(BaseModel):
    claude_enabled: bool | None = None
    codex_enabled: bool | None = None
    thresholds: list[int] | None = Field(default=None, max_length=5)


def _codex_home() -> Path:
    import os

    return Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")).expanduser()


async def refresh(app: FastAPI, force: bool = False) -> None:
    """사용량을 새로 읽고 이력·임계치 이벤트를 남긴다(백그라운드 폴러와 새로 고침 버튼이 쓴다)."""
    monitor: svc.UsageMonitor = app.state.usage
    settings = app.state.settings
    with app.state.session_factory() as db:
        conf = svc.get_settings(db)
    readings: list[svc.ProviderReading] = []
    if conf["claude_enabled"] and (force or monitor.claude_due()):
        if monitor.cli_version is None:
            from ai_org.api.system import _runtime

            info = await asyncio.to_thread(_runtime(settings).detect)
            monitor.cli_version = info.version or ""
        reading = await asyncio.to_thread(svc.fetch_claude, settings.claude_home, monitor.cli_version)
        monitor.claude_fetched(reading)
        readings.append(reading)
    if conf["codex_enabled"]:
        readings.append(await asyncio.to_thread(svc.read_codex, _codex_home()))
    for reading in readings:
        monitor.last[reading.id] = reading
        with app.state.session_factory() as db:
            for window_id, previous, current in svc.record(db, reading):
                threshold = svc.crossed_threshold(previous, current, conf["thresholds"])
                if threshold is None:
                    continue
                label = svc.WINDOW_LABELS.get(window_id, window_id)
                summary = f"{reading.name} {label} 사용량 {current:.0f}% — {threshold}% 도달"
                db.add(ActivityEvent(kind="usage.threshold", summary=summary))
                db.commit()
                app.state.runs.bus.publish(
                    "usage.threshold",
                    provider=reading.id,
                    window=window_id,
                    threshold=threshold,
                    percent=round(current, 1),
                    summary=summary,
                )
    app.state.runs.bus.publish("usage.updated")


async def poll(app: FastAPI, interval_s: float) -> None:
    while True:
        with contextlib.suppress(Exception):  # 폴링 실패는 다음 주기에 다시 시도
            await refresh(app)
        await asyncio.sleep(interval_s)


def _payload(request: Request, db: DB) -> dict[str, Any]:
    monitor: svc.UsageMonitor = request.app.state.usage
    conf = svc.get_settings(db)
    providers: list[dict[str, Any]] = []
    for pid, name, enabled in (
        ("claude", "Claude", conf["claude_enabled"]),
        ("codex", "Codex", conf["codex_enabled"]),
    ):
        reading = monitor.last.get(pid)
        if not enabled:
            providers.append(
                {
                    "id": pid,
                    "name": name,
                    "state": "disabled",
                    "windows": [],
                    "plan": None,
                    "observed_at": None,
                    "message": None,
                }
            )
            continue
        if reading is None:
            providers.append(
                {
                    "id": pid,
                    "name": name,
                    "state": "pending",
                    "windows": [],
                    "plan": None,
                    "observed_at": None,
                    "message": "아직 조회하지 않았습니다.",
                }
            )
            continue
        providers.append(
            {
                "id": pid,
                "name": name,
                "state": reading.state,
                "plan": reading.plan,
                "observed_at": reading.observed_at.isoformat() if reading.observed_at else None,
                "message": reading.message,
                "windows": [svc.window_json(db, pid, w) for w in reading.windows],
            }
        )
    return {"settings": conf, "providers": providers}


@router.get("")
def get_usage(request: Request, db: DB) -> dict[str, Any]:
    return _payload(request, db)


@router.post("/refresh")
async def refresh_usage(request: Request, db: DB) -> dict[str, Any]:
    await refresh(request.app)
    return _payload(request, db)


@router.put("/settings")
async def put_usage_settings(body: UsageSettingsIn, request: Request, db: DB) -> dict[str, Any]:
    values = body.model_dump(exclude_none=True)
    if "thresholds" in values and not all(1 <= t <= 100 for t in values["thresholds"]):
        raise HTTPException(422, "임계치는 1~100 사이여야 합니다.")
    turned_on_claude = values.get("claude_enabled") is True and not svc.get_settings(db)["claude_enabled"]
    svc.put_settings(db, values)
    if turned_on_claude:
        await refresh(request.app, force=True)
    return _payload(request, db)


@router.get("/history")
def usage_history(db: DB, provider: str, window: str, hours: int = 24) -> list[dict[str, Any]]:
    return svc.history(db, provider, window, max(1, min(hours, 24 * 30)))
