"""Web engine adapter — wraps entropy_os.engines.web.DesignEngine behind the contract.

The engine's pipeline (intent → 6-worker site research → design KG matching →
gated synthesis → copy + Next.js generation → review agents → auto-improve →
optional build gate → DataHub) runs untouched.
"""

from __future__ import annotations

import os

from ..contract import ArtifactRef, CapabilitySpec, Determinism, ExecuteRequest, FieldSpec
from ..llm import build_llm
from .base import Emit, LeafAdapter, Vouch


class WebAdapter(LeafAdapter):
    name = "design-engine"
    description = ("Website generation: real-site trait research, design "
                   "knowledge graph with priors, gated design synthesis, "
                   "copywriting, Next.js code generation, review agents "
                   "with auto-improve and an optional build gate.")
    datahub_platform = "design-engine"
    member_key = "web"
    engine_module = "entropy_os.engines.web.engine"
    events_emitted = ["SiteGenerationProgress", "SiteGenerated"]

    def __init__(self):
        super().__init__()
        self._engine = None

    def _get(self):
        if self.llm_changed():
            self._engine = None       # rebuilt below against the new routing
        if self._engine is None:
            from entropy_os.engines.web.engine import DesignEngine
            self._engine = DesignEngine(
                llm=build_llm(),      # None on local → the engine's own client
                brave_key=os.environ.get("BRAVE_SEARCH_API_KEY", ""),
                serper_key=os.environ.get("SERPER_API_KEY", ""),
                datahub_gms=os.environ.get("DATAHUB_GMS",
                                           "http://localhost:8080"))
        return self._engine

    def capabilities(self) -> list[CapabilitySpec]:
        return [CapabilitySpec(
            name="web.generate_site",
            summary="Turn a brief into a reviewed Next.js site informed by "
                    "real-site design research and accumulated design memory.",
            long_running=True,
            inputs={
                "request": FieldSpec(type="string", required=True,
                                     description="the site brief"),
                "build_gate": FieldSpec(type="boolean",
                                        description="run npm install + next "
                                                    "build as a hard gate"),
            },
            outputs={
                "project_id": FieldSpec(),
                "out_dir": FieldSpec(),
                "scores": FieldSpec(type="object"),
                "pages": FieldSpec(type="array"),
            },
            tags=["web", "generation", "design"])]

    async def _run(self, req: ExecuteRequest, emit: Emit, vouch: Vouch):
        request = str(req.inputs.get("request", "")).strip()
        if not request:
            raise ValueError("web.generate_site requires inputs.request")
        engine = self._get()

        def log(line) -> None:
            emit("SiteGenerationProgress", subject=request[:80],
                 line=str(line))

        site = await engine.generate(
            request, build_gate=bool(req.inputs.get("build_gate", False)),
            log=log)

        urn = self.dataset_urn(f"project.{site.project_id}")
        scores = site.review.scores if site.review else {}
        pages = [p.kind.value for p in site.design_system.pages]

        # The review agents are static analysis over the generated tree —
        # regex and JSON parsing, no model in the loop — so their scores are
        # facts about the output rather than opinions about it.
        if site.review is not None:
            # Imported here, not at module scope: health() exists to REPORT an
            # unimportable engine, which it cannot do if importing this adapter
            # already failed for the same reason.
            from entropy_os.engines.web.models import ReviewSeverity

            for agent_name, score in scores.items():
                findings = [f for f in site.review.findings
                            if f.agent == agent_name]
                blocking = [f.message for f in findings
                            if f.severity is ReviewSeverity.BLOCKER]
                vouch(gate=f"web.review.{agent_name}",
                      determinism=Determinism.HARD,
                      # A score is a summary; a BLOCKER is the verdict. An
                      # agent passes when it found nothing blocking, not when
                      # its number looks respectable.
                      passed=not blocking,
                      evidence=(f"score {score}/100; "
                                + ("; ".join(blocking[:5]) if blocking
                                   else "no blocking findings")),
                      score=score, findings=len(findings),
                      blockers=len(blocking))

            # The build gate is the only ground truth here: npm actually
            # builds the site or it does not. `None` means node was missing,
            # so the gate never ran — which is reported as not-passed with
            # the reason, never quietly folded into success.
            build_ok = site.review.build_ok
            vouch(gate="web.build",
                  determinism=Determinism.HARD,
                  passed=build_ok is True,
                  evidence=(
                      "next build succeeded" if build_ok is True
                      else ("next build FAILED: "
                            + (site.review.build_log_tail or "")[-400:])
                      if build_ok is False
                      else "build gate did not run (npm unavailable) — "
                           "unverified, not passed"),
                  ran=build_ok is not None)

        emit("SiteGenerated", subject=urn, project_id=site.project_id,
             product_name=site.intent.product_name,
             industry=site.intent.industry, files_written=site.files_written,
             pages=pages, scores=scores,
             build_ok=site.review.build_ok if site.review else None)

        outputs = {
            "project_id": site.project_id,
            "product_name": site.intent.product_name,
            "industry": site.intent.industry,
            "out_dir": str(site.out_dir),
            "files_written": site.files_written,
            "pages": pages,
            "dark_mode": site.design_system.dark_mode,
            "scores": scores,
            "build_ok": site.review.build_ok if site.review else None,
            "improve_rounds": site.improve_rounds,
        }
        artifacts = [ArtifactRef(
            kind="site", path=str(site.out_dir),
            description=f"generated site: {site.intent.product_name}")]
        return outputs, artifacts, [urn], []

    async def aclose(self) -> None:
        if self._engine is not None:
            await self._engine.aclose()
            self._engine = None
