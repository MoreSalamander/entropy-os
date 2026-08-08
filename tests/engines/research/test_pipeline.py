"""Planner, extraction gate, and the parallel orchestrator."""

from __future__ import annotations

import asyncio
import time

from entropy_os.engines.research.extraction.extractor import EvidenceExtractor
from entropy_os.engines.research.graphs.context_graph import ContextGraph
from entropy_os.engines.research.llm.client import FakeLLM
from entropy_os.engines.research.models import RawDoc, SourceCategory, SourceStatus
from entropy_os.engines.research.orchestrator.orchestrator import ResearchOrchestrator
from entropy_os.engines.research.orchestrator.queue import AsyncioQueueBackend
from entropy_os.engines.research.planner.planner import AGENT_ARCHETYPES, ResearchPlanner
from entropy_os.engines.research.sources.base import SourceAdapter
from entropy_os.engines.research.storage.ledger import Ledger

from .conftest import make_doc


class TestPlanner:
    async def test_llm_down_still_yields_working_plan(self):
        planner = ResearchPlanner(FakeLLM(up=False))
        plan = await planner.plan("AI hardware", ["arxiv", "github", "wikipedia"])
        assert plan.topic == "AI hardware"
        assert plan.agents, "fallback plan must still staff agents"
        for agent in plan.agents:
            assert agent.queries  # every agent has at least the topic query
            assert set(agent.sources) <= {"arxiv", "github", "wikipedia"}

    async def test_roster_filtered_to_live_sources(self):
        proposal = {"domain": "hardware", "key_entities": ["TPU", "HBM"],
                    "research_questions": ["q1"], "unknowns": ["u1"],
                    "conflicting_viewpoints": ["v1"],
                    "query_variants": ["AI accelerators", "ML chips"]}
        planner = ResearchPlanner(FakeLLM({"plan": [proposal]}))
        plan = await planner.plan("AI hardware", ["arxiv"])
        # only archetypes that map onto arxiv survive; patent agent must vanish
        names = {a.name for a in plan.agents}
        assert "Academic Research Agent" in names
        assert "Patent Agent" not in names

    async def test_kg_known_becomes_context_not_gap(self):
        proposal = {"domain": "d", "key_entities": ["TPU", "NewThing"],
                    "research_questions": ["q"], "unknowns": [],
                    "conflicting_viewpoints": [], "query_variants": []}
        planner = ResearchPlanner(FakeLLM({"plan": [proposal]}))
        plan = await planner.plan("chips", ["arxiv"], kg_known=["TPU"])
        assert "TPU" in plan.known_context
        assert plan.knowledge_gaps == ["NewThing"]  # known entity is not a gap

    def test_all_ten_spec_archetypes_defined(self):
        assert len(AGENT_ARCHETYPES) == 10


GOOD_EXTRACTION = {
    "entities": [
        {"name": "Transformer", "type": "technology", "description": "attention architecture"},
        {"name": "GPU Acceleration", "type": "technology", "description": "parallel compute"},
    ],
    "claims": [
        {"statement": "Transformers dominate sequence modeling",
         "entities": ["Transformer"], "polarity": "asserts", "excerpt": "…dominate…"},
        {"statement": "orphan claim", "entities": ["NotExtracted"],
         "polarity": "asserts", "excerpt": "x"},          # must be rejected
    ],
    "relationships": [
        {"subject": "Transformer", "predicate": "optimized_by", "object": "GPU Acceleration"},
        {"subject": "Transformer", "predicate": "bogus_pred", "object": "GPU Acceleration"},  # rejected
        {"subject": "Ghost", "predicate": "uses", "object": "Transformer"},                    # rejected
    ],
}


class TestExtractionGate:
    async def test_gate_rejects_unbound_and_invalid(self):
        ex = EvidenceExtractor(FakeLLM({"extract": [GOOD_EXTRACTION]}))
        result = await ex.extract(make_doc(), prior=0.8)
        assert len(result.entities) == 2
        # 1 real claim + 1 synthetic relationship claim; orphan rejected
        statements = [c.statement for c in result.claims]
        assert "Transformers dominate sequence modeling" in statements
        assert not any("orphan" in s for s in statements)
        assert len(result.relationships) == 1
        assert result.rejected == 3

    async def test_evidence_is_deterministic_provenance(self):
        ex = EvidenceExtractor(FakeLLM({"extract": [GOOD_EXTRACTION]}))
        doc = make_doc(url="https://arxiv.org/abs/1706.03762", source="arxiv")
        result = await ex.extract(doc, prior=0.8)
        for claim in result.claims:
            assert claim.evidence, "every stored claim must carry evidence"
            for ev in claim.evidence:
                assert ev.url == doc.url          # provenance comes from the doc,
                assert ev.source == "arxiv"       # never from the LLM
                assert 0.05 <= ev.reliability <= 0.99

    async def test_llm_down_degrades_to_metadata_only(self):
        ex = EvidenceExtractor(FakeLLM(up=False))
        result = await ex.extract(make_doc(title="Some Paper"), prior=0.8)
        assert ex.degraded is True
        assert len(result.entities) == 1          # the doc itself
        assert result.claims == []                # nothing fabricated


class SlowFakeAdapter(SourceAdapter):
    """Returns one unique doc per query after a fixed delay — used to prove
    the fan-out actually runs concurrently."""
    category = SourceCategory.WEB
    reliability_prior = 0.5
    min_interval_s = 0.0
    concurrency = 10

    def __init__(self, name: str, delay: float):
        super().__init__(client=None)
        self.name = name
        self.delay = delay

    async def _search(self, query: str, k: int) -> list[RawDoc]:
        await asyncio.sleep(self.delay)
        return [RawDoc(url=f"https://{self.name}/{abs(hash(query))}",
                       title=f"{self.name}:{query}", source=self.name,
                       category=self.category, text=f"text about {query}")]


class FakeRegistry:
    def __init__(self, adapters):
        self.adapters = {a.name: a for a in adapters}

    def get(self, name):
        return self.adapters.get(name)


class TestOrchestrator:
    async def _run(self, plan, adapters, tmp_path, concurrency=16):
        registry = FakeRegistry(adapters)
        ledger = Ledger(f"sqlite+aiosqlite:///{tmp_path}/ledger.db")
        await ledger.init()
        orch = ResearchOrchestrator(
            registry, EvidenceExtractor(FakeLLM({"extract": [GOOD_EXTRACTION]})),
            ledger, AsyncioQueueBackend(),
            global_concurrency=concurrency, extract_concurrency=8)
        cg = ContextGraph("session_test", plan)
        stats = await orch.run(plan, cg)
        await ledger.close()
        return cg, stats

    async def test_true_parallel_fanout(self, plan, tmp_path):
        # 3 sources × 4 queries = 12 tasks × 0.15s. Sequential ≈ 1.8s;
        # parallel must land far under that.
        from entropy_os.engines.research.models import AgentSpec
        plan.agents = [AgentSpec(name="A", focus="f",
                                 sources=["s1", "s2", "s3"],
                                 queries=["q1", "q2", "q3", "q4"])]
        adapters = [SlowFakeAdapter(f"s{i}", 0.15) for i in (1, 2, 3)]
        t0 = time.monotonic()
        cg, stats = await self._run(plan, adapters, tmp_path)
        elapsed = time.monotonic() - t0
        assert stats["tasks_spawned"] == 12
        assert stats["docs_fetched"] == 12
        assert elapsed < 1.2, f"fan-out ran sequentially ({elapsed:.2f}s)"
        assert len(cg.claims) > 0  # extractions streamed into the context graph

    async def test_dedupe_within_and_across_runs(self, plan, tmp_path):
        from entropy_os.engines.research.models import AgentSpec
        # two agents hitting the same source+query produce identical docs
        plan.agents = [
            AgentSpec(name="A", focus="f", sources=["s1"], queries=["same"]),
            AgentSpec(name="B", focus="f", sources=["s1"], queries=["same"]),
        ]
        adapters = [SlowFakeAdapter("s1", 0.01)]
        _cg, stats = await self._run(plan, adapters, tmp_path)
        assert stats["docs_extracted"] == 1
        assert stats["docs_deduped_or_known"] == 1

        # a second SESSION over the same ledger must skip the known doc
        adapters2 = [SlowFakeAdapter("s1", 0.01)]
        _cg2, stats2 = await self._run(plan, adapters2, tmp_path)
        assert stats2["docs_extracted"] == 0
        assert stats2["docs_deduped_or_known"] == 2

    async def test_needs_key_adapter_contributes_nothing(self, plan, tmp_path):
        from entropy_os.engines.research.models import AgentSpec
        adapter = SlowFakeAdapter("keyed", 0.01)
        adapter.status = SourceStatus.NEEDS_KEY
        plan.agents = [AgentSpec(name="A", focus="f", sources=["keyed"], queries=["q"])]
        _cg, stats = await self._run(plan, [adapter], tmp_path)
        assert stats["docs_fetched"] == 0  # fail-closed
