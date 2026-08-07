"""DataHub Context Graph emission — the session graph, published to a REAL
DataHub instance as first-class metadata.

Model on the DataHub side:
  * one dataset per research SESSION   urn:...:research-engine.session.<id>
  * one dataset per SOURCE that contributed   urn:...:research-engine.source.<name>
  * UpstreamLineage: session dataset ← every contributing source dataset,
    so the DataHub lineage view IS the research provenance graph
  * datasetProperties.customProperties carry the verification ledger:
    entity/claim counts, verified vs uncertain, contradiction count,
    per-source doc counts — provenance as metadata, not prose

Implementation detail that matters: this speaks GMS's classic restli ingest
endpoint over plain httpx — no acryl-datahub SDK dependency, so it installs
on any Python and works against a stock quickstart at localhost:8080.
`enabled: auto` probes GMS and switches itself on only when GMS answers;
failures degrade to a status string, never break a research run.
"""

from __future__ import annotations

import httpx

from ..config import DataHubConfig
from .context_graph import ContextGraph


class DataHubBridge:
    def __init__(self, cfg: DataHubConfig):
        self.cfg = cfg
        self.enabled = False
        self.status = "disabled by config"

    def _dataset_urn(self, name: str) -> str:
        return (f"urn:li:dataset:(urn:li:dataPlatform:{self.cfg.platform},"
                f"{name},{self.cfg.env})")

    async def probe(self) -> bool:
        """Resolve `auto`: enabled iff GMS answers /health."""
        want = self.cfg.enabled
        if want is False or want == "false":
            return False
        try:
            async with httpx.AsyncClient(timeout=4.0) as c:
                r = await c.get(f"{self.cfg.gms_url}/health")
                self.enabled = r.status_code == 200
        except httpx.HTTPError:
            self.enabled = False
        if not self.enabled and want in (True, "true"):
            self.status = f"enabled in config but GMS unreachable at {self.cfg.gms_url}"
        elif not self.enabled:
            self.status = f"auto: GMS not running at {self.cfg.gms_url}"
        else:
            self.status = f"live → {self.cfg.gms_url}"
        return self.enabled

    async def _ingest_dataset(self, client: httpx.AsyncClient, urn: str,
                              description: str, custom: dict[str, str],
                              upstreams: list[str] | None = None) -> None:
        aspects: list[dict] = [{
            "com.linkedin.dataset.DatasetProperties": {
                "description": description[:900],
                "customProperties": {k: str(v)[:400] for k, v in custom.items()},
            }
        }]
        if upstreams:
            aspects.append({
                "com.linkedin.dataset.UpstreamLineage": {
                    "upstreams": [{"dataset": u, "type": "TRANSFORMED"}
                                  for u in upstreams]
                }
            })
        snapshot = {"entity": {"value": {
            "com.linkedin.metadata.snapshot.DatasetSnapshot": {
                "urn": urn, "aspects": aspects}}}}
        r = await client.post(f"{self.cfg.gms_url}/entities?action=ingest",
                              json=snapshot,
                              headers={"X-RestLi-Protocol-Version": "2.0.0"})
        r.raise_for_status()

    async def emit_session(self, cg: ContextGraph, verified: int,
                           uncertain: int, contradictions: int,
                           source_doc_counts: dict[str, int]) -> str:
        """Publish one finished session. Returns a human-readable status."""
        if not self.enabled:
            return self.status
        session_urn = self._dataset_urn(f"session.{cg.session_id}")
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                # Source datasets first (lineage upstreams must exist)
                source_urns = []
                for source, count in sorted(source_doc_counts.items()):
                    if count <= 0:
                        continue
                    urn = self._dataset_urn(f"source.{source}")
                    await self._ingest_dataset(
                        client, urn,
                        f"research-engine source adapter: {source}",
                        {"adapter": source, "last_session_docs": count})
                    source_urns.append(urn)

                await self._ingest_dataset(
                    client, session_urn,
                    f"Research session: {cg.plan.topic}",
                    {
                        "topic": cg.plan.topic,
                        "session_id": cg.session_id,
                        "entities": len(cg.entities),
                        "claims": len(cg.claims),
                        "relationships": len(cg.relationships),
                        "claims_verified": verified,
                        "claims_uncertain": uncertain,
                        "contradictions_confirmed": contradictions,
                        "open_questions": len(cg.open_questions),
                    },
                    upstreams=source_urns)
            self.status = f"emitted {session_urn} with {len(source_urns)} lineage upstreams"
        except httpx.HTTPError as e:
            self.status = f"emission failed: {e}"
        return self.status
