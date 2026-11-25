"""알림 센터: 이벤트 버스에서 사람에게 알릴 일만 골라 알림으로 만든다.

알림 대상(사실 이벤트만):
- 승인 요청(approval.requested)
- 사용자 대화의 응답 완료·실패(message.completed, 위임으로 생긴 하위 실행은 제외 — 위임자가 취합해 보고한다)
- 사용량 임계치 도달(usage.threshold)

만든 알림은 버스에 `notify`로 다시 보내(웹 브라우저 알림) 최근 100개를 기억한다(데스크톱 앱이 커서로 가져감).
DB에 따로 저장하지 않는다 — 같은 사실은 활동 기록·승인·메시지에 이미 있다.
"""

from __future__ import annotations

from collections import deque
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from ai_org.models import Agent
from ai_org.services.bus import EventBus

MAX_KEEP = 100
BODY_MAX = 120


def _clip(text: str, limit: int = BODY_MAX) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


class Notifier:
    def __init__(self, bus: EventBus, factory: sessionmaker[Session]) -> None:
        self.bus = bus
        self.factory = factory
        self.items: deque[dict[str, Any]] = deque(maxlen=MAX_KEEP)
        self.seq = 0

    async def run(self) -> None:
        with self.bus.subscribe() as queue:
            while True:
                event = await queue.get()
                self.handle(event)

    def handle(self, event: dict[str, Any]) -> dict[str, Any] | None:
        note = self.convert(event)
        if note is None:
            return None
        self.seq += 1
        note = {"id": self.seq, "at": datetime.now(UTC).isoformat(), **note}
        self.items.append(note)
        self.bus.publish("notify", notification=note)
        return note

    def since(self, after: int) -> list[dict[str, Any]]:
        return [n for n in self.items if n["id"] > after]

    def _agent_name(self, agent_id: object) -> str:
        if not isinstance(agent_id, str):
            return "에이전트"
        with self.factory() as db:
            agent = db.get(Agent, agent_id)
            return agent.name if agent else "에이전트"

    def convert(self, event: dict[str, Any]) -> dict[str, Any] | None:
        kind = event.get("type")
        if kind == "approval.requested":
            a = event.get("approval") or {}
            target = f" {_clip(str(a.get('target') or ''), 80)}" if a.get("target") else ""
            return {
                "kind": "approval",
                "title": "승인 요청",
                "body": f"{a.get('agent_name') or '에이전트'}: {a.get('tool') or '도구'}{target}",
                "url": f"/command/{event.get('conversation_id')}",
            }
        if kind == "message.completed":
            m = event.get("message") or {}
            if m.get("role") != "assistant" or (m.get("data") or {}).get("delegated_by"):
                return None
            name = self._agent_name(m.get("agent_id"))
            url = f"/command/{m.get('conversation_id')}"
            if m.get("status") == "done":
                body = f"{name}: {_clip(m.get('content') or '')}"
                return {"kind": "done", "title": "작업 완료", "body": body, "url": url}
            if m.get("status") == "error":
                body = f"{name}: {_clip(m.get('error') or '')}"
                return {"kind": "failed", "title": "작업 실패", "body": body, "url": url}
            return None
        if kind == "usage.threshold":
            body = str(event.get("summary") or "")
            return {"kind": "usage", "title": "사용량 경고", "body": body, "url": "/usage"}
        return None
