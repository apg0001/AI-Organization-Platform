"""프로세스 내 이벤트 버스. WebSocket 구독자에게 실시간 이벤트를 나눠 준다.

단일 사용자 로컬 앱이라 외부 브로커 없이 asyncio.Queue로 충분하다. 느린 구독자는 이벤트를 잃고
(최대 크기 초과 시 버림), 다시 연결해 REST로 최신 상태를 받는다.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

QUEUE_SIZE = 1000


class EventBus:
    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[dict[str, Any]]] = set()

    def publish(self, event_type: str, **payload: Any) -> None:
        event = {"type": event_type, "at": datetime.now(UTC).isoformat(), **payload}
        for queue in list(self._subscribers):
            with contextlib.suppress(asyncio.QueueFull):
                queue.put_nowait(event)

    @contextmanager
    def subscribe(self) -> Iterator[asyncio.Queue[dict[str, Any]]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=QUEUE_SIZE)
        self._subscribers.add(queue)
        try:
            yield queue
        finally:
            self._subscribers.discard(queue)

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)
