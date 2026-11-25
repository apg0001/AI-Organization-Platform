from __future__ import annotations

import io
import json
import time
import urllib.error
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from ai_org.config import Settings
from ai_org.services import usage as svc

TOKEN = "sk-ant-oat-SECRET-TOKEN-123"


class FakeResponse(io.BytesIO):
    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def write_creds(settings: Settings, expires_in_s: float = 3600) -> None:
    (settings.claude_home / ".credentials.json").write_text(
        json.dumps(
            {
                "claudeAiOauth": {
                    "accessToken": TOKEN,
                    "expiresAt": (time.time() + expires_in_s) * 1000,
                    "subscriptionType": "max",
                }
            }
        )
    )


def opener_for(payload: dict[str, Any], seen: list[Any]) -> Any:
    def opener(request: Any, timeout: float) -> FakeResponse:
        seen.append(request)
        return FakeResponse(json.dumps(payload).encode())

    return opener


def test_claude_fetch_parses_windows_and_never_leaks_token(settings: Settings) -> None:
    write_creds(settings)
    resets = (datetime.now(UTC) + timedelta(hours=2)).isoformat()
    seen: list[Any] = []
    reading = svc.fetch_claude(
        settings.claude_home,
        "2.1.326",
        opener=opener_for(
            {
                "five_hour": {"utilization": 42.0, "resets_at": resets},
                "seven_day": {"utilization": 10.5, "resets_at": resets},
            },
            seen,
        ),
    )
    assert reading.state == "ok" and reading.plan == "max"
    assert [(w.id, w.percent) for w in reading.windows] == [("five_hour", 42.0), ("seven_day", 10.5)]
    req = seen[0]
    assert req.get_header("Authorization") == f"Bearer {TOKEN}" and req.full_url == svc.USAGE_URL
    assert req.get_header("User-agent") == "claude-code/2.1.326"
    assert TOKEN not in repr(reading)


def test_claude_states(settings: Settings) -> None:
    assert svc.fetch_claude(settings.claude_home, None).state == "not_logged_in"
    write_creds(settings, expires_in_s=-10)
    expired = svc.fetch_claude(settings.claude_home, None, opener=lambda *a, **k: pytest.fail("no call"))
    assert expired.state == "token_expired" and "갱신" in (expired.message or "")
    write_creds(settings)

    def limited(request: Any, timeout: float) -> Any:
        raise urllib.error.HTTPError(svc.USAGE_URL, 429, "too many", {"retry-after": "120"}, None)  # type: ignore[arg-type]

    reading = svc.fetch_claude(settings.claude_home, None, opener=limited)
    assert reading.state == "rate_limited"
    monitor = svc.UsageMonitor()
    monitor.claude_fetched(reading)
    assert not monitor.claude_due()  # Retry-After 동안 다시 부르지 않는다


def test_codex_reads_latest_session(tmp_path: Path) -> None:
    sessions = tmp_path / "sessions" / "2026" / "11"
    sessions.mkdir(parents=True)
    resets = int((datetime.now(UTC) + timedelta(hours=3)).timestamp())
    lines = [
        {
            "timestamp": "2026-11-25T01:00:00Z",
            "payload": {
                "rate_limits": {"primary": {"used_percent": 5, "resets_at": resets, "window_minutes": 300}}
            },
        },
        {
            "timestamp": "2026-11-25T02:00:00Z",
            "payload": {
                "rate_limits": {
                    "primary": {"used_percent": 33, "resets_at": resets, "window_minutes": 300},
                    "secondary": {"used_percent": 12, "resets_in_seconds": 86400, "window_minutes": 10080},
                    "plan_type": "pro",
                }
            },
        },
        {"timestamp": "2026-11-25T02:01:00Z", "payload": {"type": "message"}},
    ]
    (sessions / "rollout.jsonl").write_text("\n".join(json.dumps(x) for x in lines))
    reading = svc.read_codex(tmp_path)
    assert reading.state == "ok" and reading.plan == "pro"
    assert [(w.label, w.percent) for w in reading.windows] == [("5시간", 33.0), ("주간", 12.0)]
    assert svc.read_codex(tmp_path / "none").state == "not_logged_in"


def test_pace_and_thresholds(client: TestClient) -> None:
    resets = datetime.now(UTC) + timedelta(hours=3)
    window = svc.Window("five_hour", "5시간", 0, resets, 300)
    with client.app.state.session_factory() as db:  # type: ignore[attr-defined]
        start = datetime.now(UTC) - timedelta(hours=1)
        for i, pct in enumerate([10, 20, 30, 40]):
            reading = svc.ProviderReading(
                "claude",
                "Claude",
                "ok",
                [svc.Window("five_hour", "5시간", pct, resets, 300)],
                observed_at=start + timedelta(minutes=20 * i),
            )
            crossed = svc.record(db, reading)
        window.percent = 40
        p = svc.pace(db, "claude", window)
    assert p["confidence"] == "high" and p["burn_rate_per_hour"] == pytest.approx(30, abs=0.5)
    assert p["projected_at_reset"] == 100.0 and p["exhaust_at"] is not None
    assert crossed == [("five_hour", 30, 40)]
    assert svc.crossed_threshold(70, 95, [75, 90, 100]) == 90
    assert svc.crossed_threshold(80, 85, [75, 90, 100]) is None


def test_usage_api_opt_in_and_threshold_event(
    client: TestClient, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_creds(settings)
    monkeypatch.setenv("CODEX_HOME", str(settings.home / "no-codex"))
    resets = (datetime.now(UTC) + timedelta(hours=2)).isoformat()
    values = iter([70.0, 92.0])

    def fake_fetch(claude_home: Path, cli_version: str | None) -> svc.ProviderReading:
        return svc.ProviderReading(
            "claude",
            "Claude",
            "ok",
            [svc.Window("five_hour", "5시간", next(values), svc.parse_time(resets), 300)],
            observed_at=datetime.now(UTC),
        )

    monkeypatch.setattr(svc, "fetch_claude", fake_fetch)
    data = client.get("/api/v1/usage").json()
    assert data["settings"]["claude_enabled"] is False  # 기본은 꺼짐
    assert next(p for p in data["providers"] if p["id"] == "claude")["state"] == "disabled"
    with client.websocket_connect("ws://127.0.0.1:8000/api/v1/ws") as ws:
        data = client.put("/api/v1/usage/settings", json={"claude_enabled": True}).json()
        claude = next(p for p in data["providers"] if p["id"] == "claude")
        assert claude["state"] == "ok" and claude["windows"][0]["percent"] == 70.0
        assert 0 < claude["windows"][0]["elapsed_percent"] < 100
        client.app.state.usage.next_claude_at = 0  # type: ignore[attr-defined]
        client.post("/api/v1/usage/refresh")
        event = ws.receive_json()
        while event["type"] != "usage.threshold":
            event = ws.receive_json()
    assert event["threshold"] == 90 and event["provider"] == "claude"
    assert TOKEN not in client.get("/api/v1/usage").text
    assert (
        len(client.get("/api/v1/usage/history", params={"provider": "claude", "window": "five_hour"}).json())
        == 2
    )
    assert client.put("/api/v1/usage/settings", json={"thresholds": [150]}).status_code == 422
