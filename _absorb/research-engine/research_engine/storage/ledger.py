"""Relational ledger — the audit trail and the avoid-relearning memory.

Tables:
  documents  every document ever extracted (hash, url, source, session) —
             the cross-session dedupe index
  runs       one row per research session with final stats

SQLAlchemy Core on SQLite by default; db.url in config.yaml accepts any
SQLAlchemy URL, so PostgreSQL is the documented one-line flip
(postgresql+psycopg://...) once `pip install psycopg[binary]` has run.
"""

from __future__ import annotations

import json

from sqlalchemy import (Column, DateTime, Integer, MetaData, String, Table,
                        Text, func, select)
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from ..models import RawDoc

metadata = MetaData()

documents = Table(
    "documents", metadata,
    Column("hash", String(32), primary_key=True),
    Column("url", Text, nullable=False),
    Column("title", Text),
    Column("source", String(64)),
    Column("session_id", String(64)),
    Column("fetched_at", DateTime(timezone=True), server_default=func.now()),
)

runs = Table(
    "runs", metadata,
    Column("session_id", String(64), primary_key=True),
    Column("topic", Text, nullable=False),
    Column("stats_json", Text),
    Column("started_at", DateTime(timezone=True), server_default=func.now()),
    Column("finished_at", DateTime(timezone=True)),
)


class Ledger:
    def __init__(self, url: str):
        self.engine: AsyncEngine = create_async_engine(url)

    async def init(self) -> None:
        async with self.engine.begin() as conn:
            await conn.run_sync(metadata.create_all)

    async def doc_known(self, doc_hash: str) -> bool:
        async with self.engine.connect() as conn:
            row = await conn.execute(
                select(documents.c.hash).where(documents.c.hash == doc_hash))
            return row.first() is not None

    async def record_doc(self, doc_hash: str, doc: RawDoc, session_id: str) -> None:
        async with self.engine.begin() as conn:
            # idempotent: a concurrent worker may have just written this hash
            exists = (await conn.execute(
                select(documents.c.hash).where(documents.c.hash == doc_hash))).first()
            if not exists:
                await conn.execute(documents.insert().values(
                    hash=doc_hash, url=doc.url, title=doc.title[:500],
                    source=doc.source, session_id=session_id))

    async def record_run(self, session_id: str, topic: str, stats: dict) -> None:
        async with self.engine.begin() as conn:
            await conn.execute(runs.insert().values(
                session_id=session_id, topic=topic,
                stats_json=json.dumps(stats, default=str),
                finished_at=func.now()))

    async def close(self) -> None:
        await self.engine.dispose()
