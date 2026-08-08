"""Engine assembly — the spec's final architecture, wired end to end:

    User Request → Intent Analyzer → Parallel Research Engine (6 workers)
    → Context Graph → Knowledge Graph (semantic match + priors)
    → Design Synthesis → Copywriting → Code Generator
    → Review Agents → Auto-Improve → (optional) Build Gate
    → Finished Website + Graph Memory Loop + DataHub emission

One Engine owns the long-lived pieces (LLM, Design KG, vector index,
DataHub bridge); each generate() call is a fresh project.
"""

from __future__ import annotations

from pathlib import Path

from entropy_os.engines.research.config import LLMConfig
from entropy_os.engines.research.graphs.store import NetworkXJSONStore
from entropy_os.engines.research.graphs.vector_index import VectorIndex
from entropy_os.engines.research.llm.client import LLMClient, OllamaClient

from ...paths import engine_storage
from .codegen.copywriter import Copywriter
from .codegen.project_writer import _PAGE_HREFS, ProjectWriter
from .graphs.context_graph import DesignContextGraph, new_project_id
from .graphs.datahub_bridge import DesignDataHubBridge
from .graphs.knowledge_graph import DesignKnowledgeGraph
from .models import GeneratedSite, ProjectOutcome
from .research.intent import IntentAnalyzer
from .research.orchestrator import DesignResearchOrchestrator
from .review.agents import run_build_gate, run_review
from .review.improver import AutoImprover
from .synthesis.synthesizer import DesignSynthesizer

# This engine's own accumulated knowledge and artifacts, addressed by its
# contract member key rather than by the repository it used to live in.
STORAGE = engine_storage("web")
PROJECT_ROOT = STORAGE


class DesignEngine:
    def __init__(self, llm: LLMClient | None = None,
                 storage_dir: Path | None = None,
                 brave_key: str = "", serper_key: str = "",
                 datahub_gms: str = "http://localhost:8080"):
        # 300s: heavy local models (qwen3.5-64k) can need a cold model swap
        # plus a long structured generation for a full page of copy — the
        # 120s default was observed timing pages out into house-copy fallback
        self.llm = llm or OllamaClient(LLMConfig(timeout_s=300))
        storage = storage_dir or STORAGE
        storage.mkdir(parents=True, exist_ok=True)
        vectors = VectorIndex(self.llm, path=storage / "qdrant")
        self.kg = DesignKnowledgeGraph(
            NetworkXJSONStore(storage / "design_kg.json"), vectors)
        self.storage = storage
        self.brave_key = brave_key
        self.serper_key = serper_key
        self.datahub = DesignDataHubBridge(gms_url=datahub_gms)
        self._probed = False

    # ------------------------------------------------------------------ #
    async def generate(self, request: str, out_dir: Path | None = None,
                       build_gate: bool = False,
                       log=print) -> GeneratedSite:
        if not self._probed:
            await self.datahub.probe()
            self._probed = True
        project_id = new_project_id()
        out = out_dir or (self.storage / "sites" / project_id)

        # Phase 1 — intent
        intent = await IntentAnalyzer(self.llm).analyze(request)
        log(f"[intent] {intent.industry} | audience: {', '.join(intent.audience[:3])} "
            f"| pages: {', '.join(p.value for p in intent.required_pages)}")
        log(f"[intent] semantic traits: {', '.join(intent.semantic_traits)}")

        # Phase 2+3 — parallel research into the Context Graph
        cg = DesignContextGraph(project_id, intent)
        research = DesignResearchOrchestrator(self.brave_key, self.serper_key)
        try:
            stats = await research.run(intent, cg)
        finally:
            await research.aclose()
        log(f"[research] {stats['sites_analyzed']} sites analyzed "
            f"({stats['sites_failed']} failed), {stats['traits_extracted']} traits")
        log(f"[research] {stats['competitor_note']}")

        # Phase 4 — Knowledge Graph absorption + semantic matching + priors
        for analysis in cg.analyses.values():
            await self.kg.absorb_analysis(analysis, intent.industry)
        self.kg.store.flush()
        semantic_ranked = await self.kg.semantic_match(intent.semantic_traits)
        priors = self.kg.priors_for(intent.industry)
        log(f"[kg] {self.kg.stats()['nodes_by_kind']} | semantic matches: "
            f"{len(semantic_ranked)} | past projects in industry: "
            f"{priors['past_projects']}")

        # Phase 5 — design synthesis behind deterministic gates
        ds = await DesignSynthesizer(self.llm).synthesize(cg, priors, semantic_ranked)
        log(f"[synthesis] {ds.heading_font.value}/{ds.body_font.value}, "
            f"{'dark' if ds.dark_mode else 'light'}, motion={ds.motion.value}")
        log(f"[synthesis] novelty: {ds.novelty_note}")
        log("[synthesis] inspirations: "
            + "; ".join(f"{i['site']} ({i['trait']})" for i in ds.inspirations) or "none")

        # Phase 6 — copy + code generation
        hrefs = [_PAGE_HREFS[p.kind] for p in ds.pages]
        writer_copy: dict[str, dict] = {}
        copywriter = Copywriter(self.llm)
        # sequential on purpose: a local single-GPU Ollama serializes requests
        # anyway, and firing pages concurrently just stacks queue wait into
        # each request's timeout (observed: later pages degrade to house copy)
        for plan in ds.pages:
            writer_copy[plan.kind.value] = await copywriter.write_page(
                intent, ds, plan, hrefs)
        site = ProjectWriter(out).write(intent, ds, writer_copy)
        site.project_id = project_id
        log(f"[codegen] {site.files_written} files → {out}"
            + (" (copy degraded: LLM down, house copy used)"
               if copywriter.degraded else ""))

        # Phase 7 — review + auto-improve + optional build gate
        report = run_review(out, ds)
        report, rounds = AutoImprover().improve(out, ds, report)
        if build_gate:
            log("[review] running build gate (npm install + next build)…")
            report.build_ok, report.build_log_tail = await run_build_gate(out)
        site.review = report
        site.improve_rounds = rounds
        log("[review] scores: " + ", ".join(f"{k}={v}" for k, v in report.scores.items())
            + f" | blockers: {len(report.blockers)} | auto-fix rounds: {rounds}"
            + f" | build: {report.build_ok}")

        # Phase 8 — graph memory loop + provenance emission
        section_usage: dict[str, int] = {}
        for plan in ds.pages:
            for s in plan.sections:
                section_usage[s.value] = section_usage.get(s.value, 0) + 1
        self.kg.record_outcome(ProjectOutcome(
            project_id=project_id, industry=intent.industry,
            design_system_id=ds.id, section_usage=section_usage,
            palette_mode="dark" if ds.dark_mode else "light",
            heading_font=ds.heading_font.value, motion=ds.motion.value,
            review_scores=report.scores, build_ok=report.build_ok))
        cg.save(self.storage / "projects")
        datahub_status = await self.datahub.emit_project(project_id, cg, ds, report)
        log(f"[memory] outcome recorded; datahub: {datahub_status}")
        return site

    async def aclose(self) -> None:
        self.kg.store.close()
        self.kg.vectors.close()
        if isinstance(self.llm, OllamaClient):
            await self.llm.aclose()
