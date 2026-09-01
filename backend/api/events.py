"""In-process SSE fan-out for a single backend instance (G1)."""

from __future__ import annotations

import asyncio
from collections import defaultdict

from backend.jobs.models import utc_now_iso


class EventHub:
    def __init__(self) -> None:
        self._subs: dict[str, list[asyncio.Queue[dict[str, object]]]] = defaultdict(
            list
        )

    def subscribe(self, project_id: str) -> asyncio.Queue[dict[str, object]]:
        queue: asyncio.Queue[dict[str, object]] = asyncio.Queue()
        self._subs[project_id].append(queue)
        return queue

    def unsubscribe(
        self, project_id: str, queue: asyncio.Queue[dict[str, object]]
    ) -> None:
        holders = self._subs.get(project_id, [])
        if queue in holders:
            holders.remove(queue)

    def publish(
        self, project_id: str, event_type: str, payload: dict[str, object]
    ) -> None:
        event: dict[str, object] = {
            "type": event_type,
            "at": utc_now_iso(),
            "payload": payload,
        }
        for queue in list(self._subs.get(project_id, [])):
            queue.put_nowait(event)
