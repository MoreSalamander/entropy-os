"""Web engine adapter — wraps design_engine.DesignEngine behind the contract.

The engine's pipeline (intent → 6-worker site research → design KG matching →
gated synthesis → copy + Next.js generation → review agents → auto-improve →
optional build gate → DataHub) runs untouched.
"""

from __future__ import annotations

import os

from ..contract import ArtifactRef, CapabilitySpec, ExecuteRequest, FieldSpec
from ..llm import build_llm
from .base import Emit, LeafAdapter


class WebAdapter(LeafAdapter):
    name = "design-engine"
    description = ("Website generation: real-site trait research, design "
                   "knowledge graph with priors, gated design synthesis, "
                   "copywriting, Next.js code generation, review agents "
                   "with auto-improve and an optional build gate.")
    datahub_platform = "design-engine"
    engine_module = "design_engine.engine"
    events_emitted = ["SiteGenerationProgress", "SiteGenerated"]

    def __init__(self):
        super().__init__()
        self._engine = None

    def _get(self):
        if self._engine is None:
            from design_engine.engine import DesignEngine
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

    async def _run(self, req: ExecuteRequest, emit: Emit):
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
