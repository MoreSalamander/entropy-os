"""The unified semantic event log.

Append-only JSONL on disk is the bus: every process in the composed system
(the unified app, the Temporal worker, tools) appends SemanticEvents to the
same file and reads the same history. In-memory subscribers exist only within
a process; durability and cross-process visibility come from the file itself.

Events describe what happened. Nothing in this module dispatches, routes, or
reacts — reaction is a choice each consumer makes, which is what keeps the
engines autonomous.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path

from ..contract import SemanticEvent

Subscriber = Callable[[SemanticEvent], Awaitable[None]]


class EventBus:
    def __init__(self, log_path: Path):
        self.log_path = log_path
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._subs: list[Subscriber] = []
        self._lock = asyncio.Lock()

    async def publish(self, event: SemanticEvent) -> None:
        async with self._lock:
            with self.log_path.open("a") as f:
                f.write(event.model_dump_json() + "\n")
        for sub in list(self._subs):
            try:
                await sub(event)
            except Exception:
                # A broken subscriber must never break the narration of facts.
                continue

    async def publish_all(self, events: list[SemanticEvent]) -> None:
        for e in events:
            await self.publish(e)

    def subscribe(self, sub: Subscriber) -> None:
        self._subs.append(sub)

    def recent(self, since_id: str = "", limit: int = 500) -> list[SemanticEvent]:
        """Re-read the shared file each call so events appended by OTHER
        processes (the Temporal worker, most importantly) are always visible."""
        if not self.log_path.exists():
            return []
        events: list[SemanticEvent] = []
        with self.log_path.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    events.append(SemanticEvent.model_validate_json(line))
                except Exception:
                    continue    # a torn/foreign line must not poison history
        if since_id:
            for i, e in enumerate(events):
                if e.event_id == since_id:
                    events = events[i + 1:]
                    break
        return events[-limit:]
