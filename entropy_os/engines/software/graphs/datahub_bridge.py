"""DataHub emission for software projects — the third platform in the family.

  dataset code-engine.project.<id>
    ← lineage from code-engine.research.<agent>   (what informed it)
    ← lineage from code-engine.pattern.<name>     (which KG patterns it reused)
  properties: spec fingerprint, component/entity/endpoint/test counts,
  verification results per check, repair rounds, known problems — so DataHub
  answers WHAT was built, WHAT was verified, and WHAT is broken.
"""

from __future__ import annotations

import httpx

from entropy_os.engines.research.config import DataHubConfig
from entropy_os.engines.research.graphs.datahub_bridge import DataHubBridge

from ..models import GeneratedProject


class CodeDataHubBridge(DataHubBridge):
    def __init__(self, gms_url: str = "http://localhost:8080",
                 enabled: str | bool = "auto"):
        super().__init__(DataHubConfig(enabled=enabled, gms_url=gms_url,
                                       platform="code-engine", env="PROD"))

    async def emit_project(self, project: GeneratedProject,
                           research_agents: list[str],
                           patterns: list[str]) -> str:
        if not self.enabled:
            return self.status
        urn = self._dataset_urn(f"project.{project.project_id}")
        ver = project.verification
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                upstreams = []
                for agent in research_agents:
                    a_urn = self._dataset_urn(
                        f"research.{agent.lower().replace(' ', '_')}")
                    await self._ingest_dataset(
                        client, a_urn, f"code-engine research worker: {agent}",
                        {"agent": agent})
                    upstreams.append(a_urn)
                for pattern in patterns:
                    p_urn = self._dataset_urn(f"pattern.{pattern}")
                    await self._ingest_dataset(
                        client, p_urn, f"engineering pattern: {pattern}",
                        {"pattern": pattern})
                    upstreams.append(p_urn)
                props = {
                    "project_id": project.project_id,
                    "product": project.spec.product_name,
                    "purpose": project.spec.purpose[:200],
                    "requirements": len(project.spec.requirements),
                    "components": len(project.architecture.components),
                    "entities": len(project.architecture.entities),
                    "endpoints": sum(len(c.endpoints)
                                     for c in project.architecture.components),
                    "files_written": project.files_written,
                }
                if ver:
                    for res in ver.results:
                        props[f"check_{res.check}"] = res.status.value
                    props["repair_rounds"] = ver.repair_rounds
                    props["known_problems"] = len(ver.known_problems)
                await self._ingest_dataset(
                    client, urn,
                    f"Generated software: {project.spec.product_name}",
                    props, upstreams=upstreams)
            self.status = (f"emitted {urn} with {len(upstreams)} "
                           "research+pattern lineage upstreams")
        except httpx.HTTPError as e:
            self.status = f"emission failed: {e}"
        return self.status
