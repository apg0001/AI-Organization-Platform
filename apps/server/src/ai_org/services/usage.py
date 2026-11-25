"""AI 사용량(Claude·Codex).

소유자의 GigaCharge(apg0001/AI_Agent_Usage_Widget_for_MAC, MIT)의 수집·예측 방식을 Python으로 옮겼다.

- Claude: **사용자가 켤 때만**. Claude Code CLI 로그인 토큰(`~/.claude/.credentials.json`,
  macOS 키체인)을 읽기 전용으로 써서 `https://api.anthropic.com/api/oauth/usage`(비공개 API —
  바뀔 수 있음)를 조회한다. 토큰은 저장·로그·응답에 남기지 않고 갱신(refresh)하지 않는다
  (갱신하면 CLI 로그인이 깨질 수 있다). 만료됐으면 CLI를 한 번 실행하라고 안내한다.
  최소 60초 간격, 15초 제한 시간, 서버의 Retry-After를 지킨다.
- Codex: `~/.codex/sessions/**/*.jsonl`에 CLI가 남긴 rate-limit 기록(네트워크 없음).
  오래된 값은 관측 시각과 함께 보인다.
- 이력: 사용률·초기화 시각이 바뀌거나 5분이 지나면 기록, 30일 보관.
- 소진 예측: 같은 초기화 주기의 기록에 최소제곱 선형 회귀(감소 기울기는 0).
  기록 2개·5분 이상부터, 4개·30분 이상이면 신뢰도 높음.
- 임계치: 직전 값이 임계치 미만이었다가 이상이 되면 한 번 알린다(여러 개를 넘으면 가장 높은 것만).
"""

from __future__ import annotations

import json
import platform
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ai_org.models import AppSetting, UsageSample

USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
MIN_FETCH_S = 60
REQUEST_TIMEOUT_S = 15
HISTORY_KEEP = timedelta(days=30)
SAMPLE_EVERY = timedelta(minutes=5)
DEFAULT_SETTINGS: dict[str, Any] = {
    "claude_enabled": False,
    "codex_enabled": True,
    "thresholds": [75, 90, 100],
}
WINDOW_MINUTES = {"five_hour": 300, "seven_day": 10080}
WINDOW_LABELS = {
    "five_hour": "5시간",
    "seven_day": "주간",
    "seven_day_opus": "주간(Opus)",
    "primary": "기본 한도",
    "secondary": "보조 한도",
}


@dataclass
class Window:
    id: str
    label: str
    percent: float
    resets_at: datetime | None
    window_minutes: int | None = None


@dataclass
class ProviderReading:
    id: str
    name: str
    state: str = "pending"  # ok | not_logged_in | token_expired | rate_limited | error | no_data
    windows: list[Window] = field(default_factory=list)
    plan: str | None = None
    observed_at: datetime | None = None
    message: str | None = None


def now() -> datetime:
    return datetime.now(UTC)


def parse_time(value: Any) -> datetime | None:
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, UTC)
    if isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    return None


# ── 설정 ───────────────────────────────────────────────────────────────────


def get_settings(db: Session) -> dict[str, Any]:
    row = db.get(AppSetting, "usage")
    return {**DEFAULT_SETTINGS, **(row.value if row else {})}


def put_settings(db: Session, values: dict[str, Any]) -> dict[str, Any]:
    merged = {**get_settings(db), **values}
    row = db.get(AppSetting, "usage")
    if row is None:
        db.add(AppSetting(key="usage", value=merged))
    else:
        row.value = merged
    db.commit()
    return merged


# ── Claude ─────────────────────────────────────────────────────────────────


def read_claude_credentials(claude_home: Path) -> dict[str, Any] | None:
    """CLI 로그인 정보(읽기 전용). 파일이 없으면 macOS 키체인을 본다."""
    path = claude_home / ".credentials.json"
    data: Any = None
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = None
    elif platform.system() == "Darwin":
        try:
            out = subprocess.run(
                ["/usr/bin/security", "find-generic-password", "-s", "Claude Code-credentials", "-w"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            data = json.loads(out.stdout) if out.returncode == 0 else None
        except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
            data = None
    if not isinstance(data, dict):
        return None
    oauth = data.get("claudeAiOauth", data)
    return oauth if isinstance(oauth, dict) and oauth.get("accessToken") else None


def fetch_claude(claude_home: Path, cli_version: str | None, opener: Any = None) -> ProviderReading:
    reading = ProviderReading("claude", "Claude")
    creds = read_claude_credentials(claude_home)
    if creds is None:
        reading.state, reading.message = (
            "not_logged_in",
            "Claude Code CLI에 로그인되어 있지 않습니다(`claude` 실행 후 로그인).",
        )
        return reading
    reading.plan = str(creds.get("subscriptionType") or "") or None
    expires = parse_time((creds.get("expiresAt") or 0) / 1000) if creds.get("expiresAt") else None
    if expires is not None and expires <= now():
        reading.state = "token_expired"
        reading.message = (
            "로그인 토큰이 만료되었습니다. 터미널에서 `claude`를 한 번 실행하면 갱신됩니다"
            "(이 앱은 토큰을 갱신하지 않습니다)."
        )
        return reading
    request = urllib.request.Request(
        USAGE_URL,
        headers={
            "Authorization": f"Bearer {creds['accessToken']}",
            "Content-Type": "application/json",
            "anthropic-beta": "oauth-2025-04-20",
            "User-Agent": f"claude-code/{cli_version or '2.1'}",
        },
    )
    try:
        with (opener or urllib.request.urlopen)(request, timeout=REQUEST_TIMEOUT_S) as response:
            data = json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            reading.state = "rate_limited"
            retry = exc.headers.get("retry-after") or "60"
            reading.message = f"사용량 API가 잠시 막혔습니다. {retry}초 뒤 다시 조회합니다."
            reading.observed_at = now() + timedelta(seconds=float(exc.headers.get("retry-after") or 60))
        elif exc.code in (401, 403):
            reading.state = "token_expired"
            reading.message = "로그인 토큰이 거부되었습니다. 터미널에서 `claude`를 한 번 실행해 주세요."
        else:
            reading.state, reading.message = "error", f"사용량 API 오류(HTTP {exc.code})"
        return reading
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        reading.state, reading.message = "error", f"사용량 API에 연결하지 못했습니다: {type(exc).__name__}"
        return reading
    for key in ("five_hour", "seven_day", "seven_day_opus"):
        block = data.get(key)
        if isinstance(block, dict) and isinstance(block.get("utilization"), (int, float)):
            reading.windows.append(
                Window(
                    key,
                    WINDOW_LABELS[key],
                    float(block["utilization"]),
                    parse_time(block.get("resets_at")),
                    WINDOW_MINUTES.get(key, 10080),
                )
            )
    reading.plan = str(data.get("subscription_type") or reading.plan or "") or None
    reading.state = "ok" if reading.windows else "no_data"
    reading.observed_at = now()
    return reading


# ── Codex ──────────────────────────────────────────────────────────────────


def read_codex(codex_home: Path, max_files: int = 50) -> ProviderReading:
    reading = ProviderReading("codex", "Codex")
    sessions = codex_home / "sessions"
    if not sessions.is_dir():
        reading.state, reading.message = "not_logged_in", "Codex CLI 세션 기록이 없습니다."
        return reading
    files = sorted(sessions.rglob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)[:max_files]
    expired_seen: datetime | None = None
    for file in files:
        try:
            with file.open("rb") as fh:
                fh.seek(max(0, file.stat().st_size - 256 * 1024))
                lines = fh.read().decode("utf-8", "replace").splitlines()
        except OSError:
            continue
        for line in reversed(lines):
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            limits = (record.get("payload") or {}).get("rate_limits") if isinstance(record, dict) else None
            if not isinstance(limits, dict) or (limits.get("limit_id") not in (None, "codex")):
                continue
            observed = parse_time(record.get("timestamp")) or datetime.fromtimestamp(
                file.stat().st_mtime, UTC
            )
            windows = []
            for key in ("primary", "secondary"):
                block = limits.get(key)
                if not isinstance(block, dict) or not isinstance(block.get("used_percent"), (int, float)):
                    continue
                if isinstance(block.get("resets_at"), (int, float)):
                    resets = parse_time(block["resets_at"])
                elif isinstance(block.get("resets_in_seconds"), (int, float)):
                    resets = observed + timedelta(seconds=block["resets_in_seconds"])
                else:
                    resets = None
                if resets is not None and resets <= now():
                    expired_seen = max(expired_seen or observed, observed)
                    continue  # 이미 초기화된 기간의 값은 쓰지 않는다
                minutes = block.get("window_minutes")
                label = "5시간" if minutes == 300 else "주간" if minutes == 10080 else WINDOW_LABELS[key]
                windows.append(
                    Window(
                        key,
                        label,
                        float(block["used_percent"]),
                        resets,
                        int(minutes) if isinstance(minutes, (int, float)) else None,
                    )
                )
            if windows:
                reading.windows, reading.state, reading.observed_at = windows, "ok", observed
                reading.plan = str(limits.get("plan_type") or "") or None
                return reading
    reading.state = "no_data"
    if expired_seen is not None:
        reading.message = (
            f"마지막 Codex 사용 기록({expired_seen.date().isoformat()})의 한도 기간이 지났습니다. "
            "Codex를 쓰면 새 값이 나타납니다."
        )
    else:
        reading.message = "최근 Codex 세션에 사용량 기록이 없습니다(Codex를 한 번 쓰면 나타납니다)."
    return reading


# ── 이력·예측 ──────────────────────────────────────────────────────────────


def record(db: Session, reading: ProviderReading) -> list[tuple[str, float, float]]:
    """관측값을 이력에 남기고, 넘은 임계치(창, 직전, 현재)를 돌려준다."""
    if reading.state != "ok" or reading.observed_at is None:
        return []
    crossed: list[tuple[str, float, float]] = []
    for window in reading.windows:
        last = db.scalar(
            select(UsageSample)
            .where(UsageSample.provider == reading.id, UsageSample.window_id == window.id)
            .order_by(UsageSample.observed_at.desc())
        )
        changed = (
            last is None or abs(last.percent - window.percent) >= 0.5 or last.resets_at != window.resets_at
        )
        if last is not None and not changed and reading.observed_at - last.observed_at < SAMPLE_EVERY:
            continue
        if last is not None and last.resets_at == window.resets_at:
            crossed.append((window.id, last.percent, window.percent))
        db.add(
            UsageSample(
                provider=reading.id,
                window_id=window.id,
                percent=window.percent,
                resets_at=window.resets_at,
                observed_at=reading.observed_at,
            )
        )
    db.execute(delete(UsageSample).where(UsageSample.observed_at < now() - HISTORY_KEEP))
    db.commit()
    return crossed


def crossed_threshold(previous: float, current: float, thresholds: list[int]) -> int | None:
    hit = [t for t in sorted(thresholds) if previous < t <= current]
    return hit[-1] if hit else None


def pace(db: Session, provider: str, window: Window) -> dict[str, Any]:
    """현재 초기화 주기 기록의 소진 속도(%/시간)와 초기화 시점 예상치."""
    samples = list(
        db.scalars(
            select(UsageSample)
            .where(
                UsageSample.provider == provider,
                UsageSample.window_id == window.id,
                UsageSample.resets_at == window.resets_at,
            )
            .order_by(UsageSample.observed_at)
        )
    )
    result: dict[str, Any] = {
        "burn_rate_per_hour": None,
        "projected_at_reset": None,
        "exhaust_at": None,
        "confidence": "learning",
        "samples": len(samples),
    }
    if len(samples) < 2:
        return result
    t0 = samples[0].observed_at
    xs = [(s.observed_at - t0).total_seconds() / 3600 for s in samples]
    ys = [s.percent for s in samples]
    span_h = xs[-1] - xs[0]
    if span_h < 5 / 60:
        return result
    mean_x, mean_y = sum(xs) / len(xs), sum(ys) / len(ys)
    denom = sum((x - mean_x) ** 2 for x in xs)
    slope = (
        max(0.0, sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True)) / denom)
        if denom
        else 0.0
    )
    result["burn_rate_per_hour"] = round(slope, 2)
    result["confidence"] = "high" if len(samples) >= 4 and span_h >= 0.5 else "low"
    current = window.percent
    if window.resets_at is not None:
        hours_left = max(0.0, (window.resets_at - now()).total_seconds() / 3600)
        result["projected_at_reset"] = round(min(100.0, current + slope * hours_left), 1)
        if slope > 0 and current + slope * hours_left >= 100:
            result["exhaust_at"] = (now() + timedelta(hours=(100 - current) / slope)).isoformat()
    elif slope > 0:
        result["exhaust_at"] = (now() + timedelta(hours=(100 - current) / slope)).isoformat()
    return result


def window_json(db: Session, provider: str, window: Window) -> dict[str, Any]:
    elapsed = None
    if window.resets_at is not None and window.window_minutes:
        start = window.resets_at - timedelta(minutes=window.window_minutes)
        total = window.window_minutes * 60
        elapsed = round(min(100.0, max(0.0, (now() - start).total_seconds() / total * 100)), 1)
    return {
        "id": window.id,
        "label": window.label,
        "percent": round(window.percent, 1),
        "resets_at": window.resets_at.isoformat() if window.resets_at else None,
        "window_minutes": window.window_minutes,
        "elapsed_percent": elapsed,
        **pace(db, provider, window),
    }


def history(db: Session, provider: str, window_id: str, hours: int) -> list[dict[str, Any]]:
    since = now() - timedelta(hours=hours)
    rows = db.scalars(
        select(UsageSample)
        .where(
            UsageSample.provider == provider,
            UsageSample.window_id == window_id,
            UsageSample.observed_at >= since,
        )
        .order_by(UsageSample.observed_at)
    )
    return [{"at": r.observed_at.isoformat(), "percent": r.percent} for r in rows]


class UsageMonitor:
    """주기 조회 상태(마지막 조회 시각, 마지막 결과). Claude는 최소 60초 간격을 지킨다."""

    def __init__(self) -> None:
        self.last: dict[str, ProviderReading] = {}
        self.next_claude_at = 0.0
        self.cli_version: str | None = None

    def claude_due(self) -> bool:
        return time.monotonic() >= self.next_claude_at

    def claude_fetched(self, reading: ProviderReading) -> None:
        wait = MIN_FETCH_S
        if reading.state == "rate_limited" and reading.observed_at is not None:
            wait = max(wait, int((reading.observed_at - now()).total_seconds()))
            reading.observed_at = None
        self.next_claude_at = time.monotonic() + wait
