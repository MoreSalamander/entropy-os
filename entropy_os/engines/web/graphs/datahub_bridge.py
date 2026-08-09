"""Design-flavored DataHub emission — reuses research-engine's bridge
mechanics (plain-httpx restli against GMS, auto-probe, graceful failure)
and models a website project as:

  dataset design-engine.project.<id>
    ← lineage from design-engine.site.<analyzed-site-host>  (research inputs)
  properties: intent summary, design-system fingerprint, review scores,
  build result, novelty note — the design provenance ledger as metadata.
"""

from __future__ import annotations

from urllib.parse import urlparse

import httpx

from entropy_os.engines.research.config import DataHubConfig
from entropy_os.engines.research.graphs.datahub_bridge import DataHubBridge

from ..graphs.context_graph import DesignContextGraph
from ..models import DesignSystem, ReviewReport


class DesignDataHubBridge(DataHubBridge):
    def __init__(self, gms_url: str = "http://localhost:8080",
                 enabled: str | bool = "auto"):
        super().__init__(DataHubConfig(enabled=enabled, gms_url=gms_url,
                                       platform="design-engine", env="PROD"))

    async def emit_project(self, project_id: str, cg: DesignContextGraph,
                           ds: DesignSystem, review: ReviewReport) -> str:
        if not self.enabled:
            return self.status
        project_urn = self._dataset_urn(f"project.{project_id}")
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                upstreams = []
                for url, analysis in sorted(cg.analyses.items()):
                    if not analysis.ok:
                        continue
                    host = urlparse(url).netloc or url
                    urn = self._dataset_urn(f"site.{host}")
                    await self._ingest_dataset(
                        client, urn,
                        f"analyzed design source: {host}",
                        {"category": analysis.seed_category or "discovered",
                         "traits": len(analysis.traits),
                         "worker": analysis.worker})
                    upstreams.append(urn)
                await self._ingest_dataset(
                    client, project_urn,
                    f"Generated website: {cg.intent.raw_request[:120]}",
                    {
                        "project_id": project_id,
                        "industry": cg.intent.industry,
                        "pages": ",".join(p.value for p in cg.intent.required_pages),
                        "sites_analyzed": sum(1 for a in cg.analyses.values() if a.ok),
                        "traits_extracted": len(cg.traits),
                        "heading_font": ds.heading_font.value,
                        "palette_mode": "dark" if ds.dark_mode else "light",
                        "motion": ds.motion.value,
                        "novelty": ds.novelty_note[:300],
                        **{f"score_{k.replace(' ', '_').lower()}": v
                           for k, v in review.scores.items()},
                        "build_ok": str(review.build_ok),
                    },
                    upstreams=upstreams)
            self.status = (f"emitted {project_urn} with {len(upstreams)} "
                           "design-source lineage upstreams")
        except httpx.HTTPError as e:
            self.status = f"emission failed: {e}"
        return self.status
