"""Queue backend behind the parallel fan-out.

AsyncioQueueBackend is the in-process default: a bounded asyncio.Queue plus
a worker pool, which is exactly the execution semantics the spec's diagram
asks for and comfortably runs hundreds of concurrent I/O-bound tasks.

RedisQueueBackend is the config-flip distributed variant (queue.backend=redis
+ `pip install redis`): same interface, list-based FIFO, so multiple engine
processes can share one work stream. Included so the spec's Redis lane is a
real switch, not a promise.
"""

from __future__ import annotations

import asyncio
import json
from abc import ABC, abstractmethod
from typing import Any


class QueueBackend(ABC):
    @abstractmethod
    async def put(self, item: dict[str, Any]) -> None: ...

    @abstractmethod
    async def get(self) -> dict[str, Any] | None:
        """Next item, or None when the queue is closed and drained."""

    @abstractmethod
    async def close(self) -> None: ...


class AsyncioQueueBackend(QueueBackend):
    _SENTINEL: dict = {"__closed__": True}

    def __init__(self, maxsize: int = 0):
        self.q: asyncio.Queue[dict] = asyncio.Queue(maxsize=maxsize)
        self._closed = False

    async def put(self, item: dict[str, Any]) -> None:
        if not self._closed:
            await self.q.put(item)

    async def get(self) -> dict[str, Any] | None:
        item = await self.q.get()
        if item is self._SENTINEL:
            await self.q.put(self._SENTINEL)  # let sibling workers drain too
            return None
        return item

    async def close(self) -> None:
        self._closed = True
        await self.q.put(self._SENTINEL)


class RedisQueueBackend(QueueBackend):
    def __init__(self, url: str, key: str = "entropy_os.engines.research:tasks"):
        try:
            import redis.asyncio as aioredis  # deferred: optional dependency
        except ImportError as e:
            raise RuntimeError(
                "queue.backend=redis but the driver is missing — "
                "run: pip install redis") from e
        self.r = aioredis.from_url(url)
        self.key = key
        self._closed = False

    async def put(self, item: dict[str, Any]) -> None:
        await self.r.rpush(self.key, json.dumps(item))

    async def get(self) -> dict[str, Any] | None:
        if self._closed:
            return None
        row = await self.r.blpop(self.key, timeout=2)
        if row is None:
            return None if self._closed else await self.get()
        return json.loads(row[1])

    async def close(self) -> None:
        self._closed = True
        await self.r.aclose()


def make_queue(backend: str, redis_url: str = "") -> QueueBackend:
    if backend == "redis":
        return RedisQueueBackend(redis_url)
    return AsyncioQueueBackend()
