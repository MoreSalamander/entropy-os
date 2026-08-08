"""Parallel Search Orchestration Layer.

The fan-out the spec diagrams:

    plan → (agent × source × query-variant) search tasks → queue
         → worker pool (global_concurrency workers, per-source semaphores)
         → dedupe gate (URL + content hash, session AND cross-session)
         → bounded extraction pool (LLM calls)
         → Context Graph, updated LIVE as each document lands

Concurrency model: one asyncio worker pool drains the queue; each source
adapter carries its own semaphore + politeness interval, so raising
global_concurrency to hundreds parallelizes across sources without
hammering any single API. Extraction has its own smaller pool because the
local LLM, not the network, is the throughput bottleneck.

The dedupe gate is the continuous-learning hook: the ledger remembers every
document ever extracted (by URL/content hash), and a doc seen in ANY prior
session is skipped — the engine does not relearn what it already learned.
"""

from __future__ import annotations

import asyncio
from typing import Awaitable, Callable

from ..extraction.extractor import EvidenceExtractor
from ..graphs.context_graph import ContextGraph
from ..models import ProgressEvent, RawDoc, ResearchPlan, SessionPhase
from ..sources.registry import SourceRegistry
from ..storage.ledger import Ledger
from .queue import QueueBackend

ProgressHook = Callable[[ProgressEvent], Awaitable[None]] | None


class ResearchOrchestrator:
    def __init__(self, registry: SourceRegistry, extractor: EvidenceExtractor,
                 ledger: Ledger, queue: QueueBackend,
                 global_concurrency: int = 32, extract_concurrency: int = 3,
                 max_results_per_source: int = 8,
                 progress: ProgressHook = None):
        self.registry = registry
        self.extractor = extractor
        self.ledger = ledger
        self.queue = queue
        self.global_concurrency = global_concurrency
        self.extract_sem = asyncio.Semaphore(extract_concurrency)
        self.max_results = max_results_per_source
        self.progress = progress
        # per-run counters for the report's honesty stats
        self.tasks_spawned = 0
        self.docs_fetched = 0
        self.docs_deduped = 0
        self.docs_extracted = 0
        self.rejected_items = 0

    async def _emit(self, phase: SessionPhase, message: str, **data) -> None:
        if self.progress:
            await self.progress(ProgressEvent(phase=phase, message=message, data=data))

    # ------------------------------------------------------------------ #
    # task generation
    # ------------------------------------------------------------------ #
    async def _enqueue_all(self, plan: ResearchPlan) -> None:
        """agent × source × query-variant → one task each. A 10-agent plan
        with 2-3 variants lands 60-120 tasks; the pool absorbs hundreds."""
        for agent in plan.agents:
            for source in agent.sources:
                for query in agent.queries:
                    await self.queue.put({"agent": agent.name, "source": source,
                                          "query": query,
                                          "emphasis": agent.extraction_emphasis})
                    self.tasks_spawned += 1
        await self.queue.close()

    # ------------------------------------------------------------------ #
    # worker pool
    # ------------------------------------------------------------------ #
    async def _worker(self, cg: ContextGraph, seen_this_run: set[str]) -> None:
        while True:
            task = await self.queue.get()
            if task is None:
                return
            adapter = self.registry.get(task["source"])
            if adapter is None:
                continue
            docs = await adapter.search(task["query"], self.max_results)
            self.docs_fetched += len(docs)
            for doc in docs:
                await self._process_doc(cg, task, doc, seen_this_run)

    async def _process_doc(self, cg: ContextGraph, task: dict, doc: RawDoc,
                           seen_this_run: set[str]) -> None:
        # Dedupe gate — within this run and against every prior session.
        key = doc.text_hash
        if key in seen_this_run:
            self.docs_deduped += 1
            return
        seen_this_run.add(key)
        if await self.ledger.doc_known(key):
            self.docs_deduped += 1
            return

        adapter = self.registry.get(doc.source)
        prior = adapter.reliability_prior if adapter else 0.5
        async with self.extract_sem:  # local LLM is the bottleneck, not the net
            result = await self.extractor.extract(doc, prior, task["emphasis"])
        self.docs_extracted += 1
        self.rejected_items += result.rejected

        # Context Graph evolves DURING research, per spec — not batch-at-end.
        cg.add_extraction(task["agent"], result)
        await self.ledger.record_doc(key, doc, cg.session_id)
        await self._emit(SessionPhase.EXTRACTING,
                         f"{task['agent']} ← {doc.source}: {doc.title[:60]}",
                         entities=len(cg.entities), claims=len(cg.claims))

    # ------------------------------------------------------------------ #
    # public entry point
    # ------------------------------------------------------------------ #
    async def run(self, plan: ResearchPlan, cg: ContextGraph) -> dict:
        await self._emit(SessionPhase.SEARCHING,
                         f"fan-out: {len(plan.agents)} agents over "
                         f"{len({s for a in plan.agents for s in a.sources})} live sources")
        seen_this_run: set[str] = set()
        producers = asyncio.create_task(self._enqueue_all(plan))
        workers = [asyncio.create_task(self._worker(cg, seen_this_run))
                   for _ in range(self.global_concurrency)]
        await producers
        await asyncio.gather(*workers)
        stats = {
            "tasks_spawned": self.tasks_spawned,
            "docs_fetched": self.docs_fetched,
            "docs_deduped_or_known": self.docs_deduped,
            "docs_extracted": self.docs_extracted,
            "items_rejected_by_gate": self.rejected_items,
            "extraction_degraded": self.extractor.degraded,
        }
        await self._emit(SessionPhase.SEARCHING, "fan-out complete", **stats)
        return stats
