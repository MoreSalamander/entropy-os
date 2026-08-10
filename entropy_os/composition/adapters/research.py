"""Research engine adapter — wraps entropy_os.engines.research.Engine behind the contract.

The engine's own pipeline (plan → parallel acquisition → evidence extraction
→ Context Graph → Knowledge Graph → 6-agent reasoning → report → DataHub
emission) runs untouched; this adapter only translates its front door and
narrates its typed ProgressEvents as semantic events.
"""

from __future__ import annotations

import os

from ..contract import ArtifactRef, CapabilitySpec, Determinism, ExecuteRequest, FieldSpec
from ..llm import build_llm
from .base import Emit, LeafAdapter, Vouch

# Composed runs push this engine harder than a standalone session does: the
# reasoning agents receive a much larger Context Graph, and long-context
# generations against it were observed exceeding the engine's own 120s default
# (Ollama returning 500 after exactly 2m0s, repeatedly). Raising the ceiling is
# deployment tuning, not a change to the engine — it goes through the engine's
# own public Config, so the repository stays untouched.
DEFAULT_LLM_TIMEOUT_S = 600


class ResearchAdapter(LeafAdapter):
    name = "research-engine"
    description = ("Deep research: KG-informed planning, parallel source "
                   "acquisition, evidence extraction, graph reasoning by six "
                   "agents, verified report with DataHub provenance.")
    datahub_platform = "research-engine"
    member_key = "research"
    engine_module = "entropy_os.engines.research.engine"
    events_emitted = ["ResearchPhaseAdvanced", "ResearchCompleted",
                      "KnowledgeConsolidated"]

    def __init__(self):
        super().__init__()
        self._engine = None    # constructed lazily: loads KG + vector index

    def _get(self):
        if self.llm_changed():
            self._engine = None       # rebuilt below against the new routing
        if self._engine is None:
            # Imported here, not at module top: this module is importable in
            # any venv (for tests/registry), but the real engine only exists
            # in research-engine's own environment.
            from entropy_os.engines.research.config import load_config
            from entropy_os.engines.research.engine import Engine

            cfg = load_config()
            wanted = int(os.environ.get("ONE_ENGINE_LLM_TIMEOUT_S",
                                        DEFAULT_LLM_TIMEOUT_S))
            # Only ever raise the ceiling: an operator who deliberately set a
            # longer timeout in the engine's own config keeps it.
            cfg.llm.timeout_s = max(cfg.llm.timeout_s, wanted)
            # None on the local backend, so the engine builds its own Ollama
            # client exactly as it always has. A mixed run (say, judge on
            # Claude) needs a local half too — and this engine loads its own
            # config, so the local half is built from that rather than from a
            # generic default, keeping its tuned timeout and role routing.
            from entropy_os.engines.research.llm.client import OllamaClient
            self._engine = Engine(
                cfg, llm=build_llm(local=lambda: OllamaClient(cfg.llm)))
        return self._engine

    def capabilities(self) -> list[CapabilitySpec]:
        return [CapabilitySpec(
            name="research.investigate",
            summary="Run a full research session on a topic and return the "
                    "verified report with graph/provenance references.",
            long_running=True,
            inputs={"topic": FieldSpec(type="string", required=True,
                                       description="what to research")},
            outputs={
                "session_id": FieldSpec(description="research session id"),
                "report_path": FieldSpec(description="markdown report path"),
                "sections": FieldSpec(type="array",
                                      description="report section titles"),
                "stats": FieldSpec(type="object",
                                   description="run + consolidation stats"),
            },
            tags=["research", "perception"])]

    async def _run(self, req: ExecuteRequest, emit: Emit, vouch: Vouch):
        topic = str(req.inputs.get("topic", "")).strip()
        if not topic:
            raise ValueError("research.investigate requires inputs.topic")
        engine = self._get()

        async def hook(evt) -> None:
            # The engine's own typed progress stream, re-voiced as facts.
            emit("ResearchPhaseAdvanced", subject=topic,
                 phase=evt.phase.value, message=evt.message, **evt.data)

        report, cg = await engine.research(topic, progress=hook)

        env = getattr(engine.cfg.datahub, "env", "PROD")
        session_urn = self.dataset_urn(f"session.{report.session_id}", env)
        report_path = (engine.cfg.resolve_path(engine.cfg.report.output_dir)
                       / f"{report.session_id}.md")

        # The verification gate is the hard floor between context and
        # knowledge, and it uses no model at all: a claim is verified by
        # evidence reliability and independent corroboration, both recorded
        # numbers. Contradictions are a different story — deterministic
        # pairing proposes them and a judge model confirms — so they are
        # reported as SOFT and can never read as proof.
        claims = list(cg.claims.values())
        verified = [c for c in claims if c.verified]
        vouch(gate="research.claims_verified", determinism=Determinism.HARD,
              # Research that verified nothing has not failed — it has found
              # nothing it is willing to stand behind, which is a real result
              # and must not be dressed up as one.
              passed=bool(verified),
              evidence=(f"{len(verified)}/{len(claims)} claims cleared the "
                        f"evidence floor (single source at reliability≥0.7, "
                        f"or ≥2 independent sources at ≥0.45)"),
              verified=len(verified), claims=len(claims),
              entities=len(cg.entities))
        # Citations are machine-checkable in a way prose is not: every marker
        # in the paper either resolves to a listed source or it does not.
        refs = int(report.stats.get("paper_references", 0))
        used = int(report.stats.get("paper_claims_used", 0))
        if report.stats.get("paper_path"):
            vouch(gate="research.paper_cited", determinism=Determinism.HARD,
                  passed=bool(refs and used),
                  evidence=(f"{used} verified claim(s) rendered against "
                            f"{refs} source(s); every citation resolves"),
                  references=refs, claims=used,
                  excluded=int(report.stats.get("paper_claims_excluded", 0)))

        contradictions = int(report.stats.get("contradictions", 0))
        if contradictions:
            vouch(gate="research.contradictions", determinism=Determinism.SOFT,
                  passed=False,
                  evidence=(f"{contradictions} contradiction(s) between sources "
                            f"— deterministic pairing proposed them, a judge "
                            f"model confirmed, so this is recorded opinion"),
                  count=contradictions)

        emit("ResearchCompleted", subject=session_urn, topic=topic,
             session_id=report.session_id, sections=len(report.sections),
             entities=len(cg.entities), claims=len(cg.claims),
             relationships=len(cg.relationships))
        emit("KnowledgeConsolidated", subject=topic,
             stats={k: v for k, v in report.stats.items()
                    if isinstance(v, (int, float, str))})

        outputs = {
            "topic": topic,
            "session_id": report.session_id,
            "report_path": str(report_path),
            "sections": [{"title": s.title, "items": s.item_count}
                         for s in report.sections],
            "stats": {k: v for k, v in report.stats.items()
                      if isinstance(v, (int, float, str))},
            "entities": len(cg.entities),
            "claims": len(cg.claims),
        }
        # The paper is listed FIRST because it is the artifact a reader
        # wants; the instrument-panel report stays available behind it.
        artifacts = []
        paper_path = report.stats.get("paper_path")
        if paper_path:
            artifacts.append(ArtifactRef(
                kind="paper", path=str(paper_path),
                description=f"research paper: {topic}"))
        artifacts.append(ArtifactRef(kind="report", path=str(report_path),
                                     description=f"research report: {topic}"))
        notes = [f"engine datahub: {engine.datahub.status}"]
        return outputs, artifacts, [session_urn], notes

    async def health(self):
        report = await super().health()
        report.checks["engine"] = ("constructed" if self._engine is not None
                                   else "lazy (constructs on first execute)")
        return report

    async def aclose(self) -> None:
        if self._engine is not None:
            await self._engine.aclose()
            self._engine = None
