"""Research engine adapter — wraps research_engine.Engine behind the contract.

The engine's own pipeline (plan → parallel acquisition → evidence extraction
→ Context Graph → Knowledge Graph → 6-agent reasoning → report → DataHub
emission) runs untouched; this adapter only translates its front door and
narrates its typed ProgressEvents as semantic events.
"""

from __future__ import annotations

from ..contract import ArtifactRef, CapabilitySpec, ExecuteRequest, FieldSpec
from .base import Emit, LeafAdapter


class ResearchAdapter(LeafAdapter):
    name = "research-engine"
    description = ("Deep research: KG-informed planning, parallel source "
                   "acquisition, evidence extraction, graph reasoning by six "
                   "agents, verified report with DataHub provenance.")
    datahub_platform = "research-engine"
    engine_module = "research_engine.engine"
    events_emitted = ["ResearchPhaseAdvanced", "ResearchCompleted",
                      "KnowledgeConsolidated"]

    def __init__(self):
        super().__init__()
        self._engine = None    # constructed lazily: loads KG + vector index

    def _get(self):
        if self._engine is None:
            # Imported here, not at module top: this module is importable in
            # any venv (for tests/registry), but the real engine only exists
            # in research-engine's own environment.
            from research_engine.engine import Engine
            self._engine = Engine()
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

    async def _run(self, req: ExecuteRequest, emit: Emit):
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
        artifacts = [ArtifactRef(kind="report", path=str(report_path),
                                 description=f"research report: {topic}")]
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
