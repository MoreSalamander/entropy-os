"""Engine assembly — the spec's final architecture, wired end to end.

    User Idea → Product Intelligence → Parallel Software Research
    → Context Graph → Knowledge Graph → Architecture Intelligence
    → AI Engineering Team (generation) → Verification System
    → Context Graph Update → sidecar + DataHub → cross-project memory
"""

from __future__ import annotations

from pathlib import Path

from research_engine.config import LLMConfig
from research_engine.graphs.store import NetworkXJSONStore
from research_engine.graphs.vector_index import VectorIndex
from research_engine.llm.client import LLMClient, OllamaClient

from .architecture import ArchitectAgent
from .codegen.generator import PATTERNS_APPLIED, ProjectGenerator
from .graphs.context_graph import SoftwareContextGraph
from .graphs.datahub_bridge import CodeDataHubBridge
from .graphs.knowledge_graph import SoftwareKnowledgeGraph
from .intent import IntentAnalyzer
from .models import GeneratedProject, ProjectOutcome, new_id
from .org import run_static_agents
from .research import RESEARCH_AGENTS, SoftwareResearchOrchestrator
from .verify import Verifier

PROJECT_ROOT = Path(__file__).resolve().parent.parent
STORAGE = PROJECT_ROOT / "storage_data"


class CodeEngine:
    def __init__(self, llm: LLMClient | None = None,
                 storage_dir: Path | None = None,
                 parallel_key: str = "",
                 datahub_gms: str = "http://localhost:8080"):
        # 300s: same lesson design-engine learned — cold model swaps + long
        # structured generations need headroom on local hardware
        self.llm = llm or OllamaClient(LLMConfig(timeout_s=300))
        storage = storage_dir or STORAGE
        storage.mkdir(parents=True, exist_ok=True)
        self.storage = storage
        vectors = VectorIndex(self.llm, path=storage / "qdrant")
        self.kg = SoftwareKnowledgeGraph(
            NetworkXJSONStore(storage / "software_kg.json"), vectors)
        self.parallel_key = parallel_key
        self.datahub = CodeDataHubBridge(gms_url=datahub_gms)
        self._probed = False

    # ------------------------------------------------------------------ #
    async def build(self, request: str, out_dir: Path | None = None,
                    log=print) -> GeneratedProject:
        if not self._probed:
            await self.datahub.probe()
            self._probed = True
        project_id = new_id("proj")
        out = out_dir or (self.storage / "projects" / project_id)

        # Phase 1 — Product Agent
        spec = await IntentAnalyzer(self.llm).analyze(request)
        log(f"[intent] {spec.product_name}: {len(spec.requirements)} requirements "
            f"({sum(1 for r in spec.requirements if r.priority.value == 'must')} MUST), "
            f"{len(spec.unknowns)} unknowns")

        # Phase 2 — parallel research
        research = SoftwareResearchOrchestrator(self.parallel_key)
        try:
            evidence, rstats = await research.run(spec)
        finally:
            await research.aclose()
        log(f"[research] {rstats['evidence_total']} evidence items from "
            f"{len(RESEARCH_AGENTS)} agents; parallel.ai: {rstats['parallel_ai']}")

        # Phase 4 — knowledge absorption + priors (before design, so the
        # architect sees accumulated engineering memory)
        absorbed = await self.kg.absorb_evidence(evidence)
        priors = self.kg.pattern_priors()
        log(f"[kg] absorbed {absorbed} technology facts; "
            f"{sum(1 for p in priors if p['applied'])} patterns with history")

        # Phase 5 — Architect Agent
        brief = "\n".join(f"- [{e.agent}] {e.title}: {e.summary[:100]}"
                          for e in evidence[:20])
        arch = await ArchitectAgent(self.llm).design(spec, brief, priors)
        log(f"[architecture] {len(arch.components)} components, "
            f"{len(arch.entities)} entities, "
            f"{sum(len(c.endpoints) for c in arch.components)} endpoints; "
            f"gates fixed {len(arch.validation_notes)} issues")
        for note in arch.validation_notes[:5]:
            log(f"  [gate] {note}")

        # Phase 3 — Context Graph assembled from spec + architecture + evidence
        cg = SoftwareContextGraph(project_id)
        cg.load_spec(spec)
        cg.load_architecture(arch)
        service_names = [c.name for c in arch.components if c.kind == "service"]
        for ev in evidence:
            cg.add_evidence(ev, service_names[:1])

        # Phase 6+8 — the engineering team generates
        project = ProjectGenerator(out).generate(spec, arch, cg)
        log(f"[codegen] {project.files_written} files → {out}")

        # Phase 9 — verification (ruff + pytest + the three lint agents)
        static_results = run_static_agents(out)
        verifier = Verifier(self.llm)
        report = await verifier.verify(out, cg, extra_checks=static_results,
                                       log=log)
        project.verification = report
        checks = ", ".join(f"{r.check}={r.status.value}" for r in report.results)
        log(f"[verify] {checks} | repair rounds: {report.repair_rounds} | "
            f"known problems: {len(report.known_problems)}")

        # sidecar: the software ships carrying its own self-model
        cg.save_sidecar(out)
        log(f"[model] context graph: {cg.stats()} → {out}/.code_engine/graph.json")

        # Phase 12 — cross-project memory + DataHub provenance
        outcome = ProjectOutcome(
            project_id=project_id, product_name=spec.product_name,
            stack=arch.stack,
            components=len(arch.components), entities=len(arch.entities),
            endpoints=sum(len(c.endpoints) for c in arch.components),
            tests_generated=len(cg.nodes_of_kind("test")),
            verification_passed=report.passed,
            repair_rounds=report.repair_rounds,
            patterns=PATTERNS_APPLIED + (
                ["static_frontend_over_api"]
                if any(c.name == "web_ui" for c in arch.components) else []))
        self.kg.record_outcome(outcome)
        datahub_status = await self.datahub.emit_project(
            project, RESEARCH_AGENTS, outcome.patterns)
        log(f"[memory] outcome recorded; datahub: {datahub_status}")
        return project

    async def aclose(self) -> None:
        self.kg.store.close()
        self.kg.vectors.close()
        if isinstance(self.llm, OllamaClient):
            await self.llm.aclose()
