"""Engine assembly — the spec's pipeline, wired end to end:

    User Question → Research Planning → Parallel Information Acquisition
    → Evidence Extraction → Context Graph Construction
    → Knowledge Graph Integration → Multi-Agent Reasoning
    → Research Report + Discoveries

One Engine instance owns the long-lived pieces (source fleet, KG, vector
index, ledger, LLM client); each research() call creates a fresh session
(plan, Context Graph, orchestrator run, reasoning pass, consolidation,
report, DataHub emission).
"""

from __future__ import annotations

import asyncio
from typing import Awaitable, Callable

from .agents import (AnalystAgent, ContradictionAgent, DiscoveryAgent,
                     QuestionAgent, TrendAgent, VerificationAgent)
from .config import Config, load_config
from .extraction.extractor import EvidenceExtractor
from .graphs.context_graph import ContextGraph, new_session_id
from .graphs.datahub_bridge import DataHubBridge
from .graphs.knowledge_graph import KnowledgeGraph
from .graphs.store import make_graph_store
from .graphs.vector_index import VectorIndex
from .llm.client import LLMClient, OllamaClient
from .models import Finding, ProgressEvent, ResearchReport, SessionPhase
from .orchestrator.orchestrator import ResearchOrchestrator
from .orchestrator.queue import make_queue
from .planner.planner import ResearchPlanner
from .report.builder import ReportBuilder
from .sources.registry import SourceRegistry
from .storage.ledger import Ledger

ProgressHook = Callable[[ProgressEvent], Awaitable[None]] | None


class Engine:
    def __init__(self, cfg: Config | None = None, llm: LLMClient | None = None):
        self.cfg = cfg or load_config()
        self.llm = llm or OllamaClient(self.cfg.llm)
        self.registry = SourceRegistry(self.cfg)
        self.ledger = Ledger(self.cfg.db.url)
        store = make_graph_store(
            self.cfg.graph.backend,
            self.cfg.resolve_path(self.cfg.knowledge_graph.path),
            self.cfg.graph.neo4j.uri, self.cfg.graph.neo4j.user,
            self.cfg.graph.neo4j.password)
        vectors = VectorIndex(self.llm,
                              path=self.cfg.resolve_path(self.cfg.vectors.path),
                              url=self.cfg.vectors.url)
        self.kg = KnowledgeGraph(store, vectors, self.llm,
                                 self.cfg.vectors.similarity_merge_threshold)
        self.datahub = DataHubBridge(self.cfg.datahub)
        self._initialized = False

    async def init(self) -> None:
        if self._initialized:
            return
        await self.ledger.init()
        await self.datahub.probe()
        self._initialized = True

    # ------------------------------------------------------------------ #
    async def research(self, topic: str,
                       progress: ProgressHook = None) -> tuple[ResearchReport, ContextGraph]:
        await self.init()

        async def emit(phase: SessionPhase, message: str, **data) -> None:
            if progress:
                await progress(ProgressEvent(phase=phase, message=message, data=data))

        # 1. Research Intelligence Layer — plan, KG-informed (avoid relearning)
        await emit(SessionPhase.PLANNING, f"planning research: {topic}")
        known = self.kg.known_entities_for(topic)
        planner = ResearchPlanner(self.llm, self.cfg.orchestrator.query_variants)
        plan = await planner.plan(topic, self.registry.live_names(), known)
        await emit(SessionPhase.PLANNING,
                   f"plan ready: {len(plan.agents)} agents, "
                   f"{len(plan.research_questions)} questions, "
                   f"{len(known)} entities already known")

        # 2-4. Parallel acquisition → extraction → live Context Graph
        session_id = new_session_id()
        cg = ContextGraph(session_id, plan)
        orch = ResearchOrchestrator(
            self.registry, EvidenceExtractor(self.llm), self.ledger,
            make_queue(self.cfg.queue.backend, self.cfg.queue.redis_url),
            self.cfg.orchestrator.global_concurrency,
            self.cfg.orchestrator.extract_concurrency,
            self.cfg.orchestrator.max_results_per_source,
            progress)
        run_stats = await orch.run(plan, cg)

        # 6. Multi-Agent Reasoning over the graphs.
        # Verification runs FIRST (its verdicts feed everyone downstream);
        # the four insight agents then run CONCURRENTLY.
        await emit(SessionPhase.REASONING, "graph reasoning: 6 agents")
        findings: list[Finding] = []
        findings += await VerificationAgent(self.llm).analyze(cg, self.kg)
        concurrent = await asyncio.gather(
            ContradictionAgent(self.llm).analyze(cg, self.kg),
            AnalystAgent(self.llm).analyze(cg, self.kg),
            DiscoveryAgent(self.llm).analyze(cg, self.kg),
            TrendAgent(self.llm).analyze(cg, self.kg),
        )
        for batch in concurrent:
            findings += batch
        findings += await QuestionAgent(self.llm).analyze(cg, self.kg)

        # 5+7. Knowledge Graph integration + continuous learning
        await emit(SessionPhase.CONSOLIDATING, "promoting verified knowledge into the KG")
        from .learning.consolidator import Consolidator
        consolidation = await Consolidator(
            self.kg, self.cfg.resolve_path(self.cfg.sessions.path)
        ).consolidate(cg, findings)
        await self.ledger.record_run(session_id, topic,
                                     {**run_stats, **{k: v for k, v in consolidation.items()
                                                      if not isinstance(v, dict)}})

        # Context Graph → DataHub (lineage + provenance properties)
        contradictions = sum(1 for f in findings if f.kind == "contradiction")
        # Carried into the report's stats as well, not only into DataHub. A
        # contradiction the run FOUND is part of what the run is willing to
        # say about itself, and a consumer holding the report should not have
        # to query the metadata graph to learn that the evidence disagreed.
        run_stats["contradictions"] = contradictions
        datahub_status = await self.datahub.emit_session(
            cg,
            verified=consolidation["claims_verified"],
            uncertain=consolidation["claims_total"] - consolidation["claims_verified"],
            contradictions=contradictions,
            source_doc_counts={a.name: a.docs_returned
                               for a in self.registry.adapters.values()})

        # 8. Final Research Output
        await emit(SessionPhase.REPORTING, "building the report")
        report = await ReportBuilder(self.llm).build(
            cg, findings, run_stats, self.registry.status_table(),
            consolidation, datahub_status)
        ReportBuilder.save_markdown(report,
                                    self.cfg.resolve_path(self.cfg.report.output_dir))
        await emit(SessionPhase.DONE, "research complete",
                   sections=len(report.sections))
        return report, cg

    async def aclose(self) -> None:
        await self.registry.aclose()
        await self.ledger.close()
        self.kg.store.close()
        self.kg.vectors.close()
        if isinstance(self.llm, OllamaClient):
            await self.llm.aclose()
