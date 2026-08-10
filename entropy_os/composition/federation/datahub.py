"""DataHub federation — cross-engine identity, relationships, and provenance.

The four engines already publish their own graphs to their own DataHub
platforms (research-engine, code-engine, learn-engine, design-engine). The
federation NEVER re-emits or rewrites any of that. It owns exactly one thing:
the cross-domain claims of a composed run, published under the `one-engine`
platform:

    objective.<id>      the composed run itself; lineage ← every stage
    stage.<id>.<n>-<e>  one per member execution; lineage ← the member's OWN
                        datasets (a cross-platform edge) + the previous stage
                        (the flow edge)
    concept.<slug>      identity resolution: one node naming the shared
                        subject, carrying each domain's local representation

Because stages point at datasets the engines emitted themselves, DataHub's
lineage view renders one composed run as a single graph spanning five
platforms — federation without flattening, visible in the product.

Implementation matches the engines' proven bridge style: plain-httpx restli
ingest against GMS, probe-to-enable, degrade to a status string on failure —
provenance emission must never break an objective.
"""

from __future__ import annotations

import httpx

from ..contract import ExecuteResult, now_iso
from .semantics import primitive_for, slugify


class FederationBridge:
    def __init__(self, gms_url: str = "http://localhost:8080",
                 platform: str = "one-engine", env: str = "PROD",
                 mirror: bool = False):
        self.gms_url = gms_url.rstrip("/")
        self.platform = platform
        self.env = env
        self.enabled = False
        self.status = "not probed"
        # A mirror serves runs that already happened somewhere else. Their
        # provenance was published to DataHub on the machine that made them,
        # and it is already inside the artifacts and the event log this
        # deployment is showing. So there is no GMS here to reach and nothing
        # this deployment could emit — reporting "not reachable" would name a
        # missing organ it was never trying to have.
        self.mirror = mirror

    def dataset_urn(self, name: str, platform: str | None = None) -> str:
        return (f"urn:li:dataset:(urn:li:dataPlatform:"
                f"{platform or self.platform},{name},{self.env})")

    async def probe(self) -> bool:
        if self.mirror:
            self.enabled = False
            self.status = ("mirror — provenance was made on the authoring "
                           "machine and travels inside these artifacts")
            return False
        try:
            async with httpx.AsyncClient(timeout=4.0) as c:
                r = await c.get(f"{self.gms_url}/health")
                self.enabled = r.status_code == 200
        except httpx.HTTPError:
            self.enabled = False
        self.status = (f"live → {self.gms_url}" if self.enabled
                       else f"GMS not reachable at {self.gms_url}")
        return self.enabled

    async def _ingest(self, client: httpx.AsyncClient, urn: str,
                      description: str, custom: dict,
                      upstreams: list[str] | None = None) -> None:
        aspects: list[dict] = [{
            "com.linkedin.dataset.DatasetProperties": {
                "description": description[:900],
                "customProperties": {k: str(v)[:400]
                                     for k, v in custom.items()},
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
        r = await client.post(f"{self.gms_url}/entities?action=ingest",
                              json=snapshot,
                              headers={"X-RestLi-Protocol-Version": "2.0.0"})
        r.raise_for_status()

    # ----------------------------------------------------------------- #
    # the federation's three dataset kinds
    # ----------------------------------------------------------------- #
    async def emit_concept(self, subject: str,
                           representations: dict[str, str],
                           born_in: str = "") -> str:
        """Identity: one URN for the shared concept, listing every domain's
        local representation of it ("are these the same entity?" answered
        affirmatively, with receipts)."""
        slug = slugify(subject)
        urn = self.dataset_urn(f"concept.{slug}")
        if not self.enabled:
            return urn
        custom = {"subject": subject, "primitive": "Concept",
                  "identified_at": now_iso(), **representations}
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                await self._ingest(client, urn,
                                   f"Cross-domain concept: {subject}",
                                   custom,
                                   upstreams=[born_in] if born_in else None)
        except httpx.HTTPError as e:
            self.status = f"concept emission failed: {e}"
        return urn

    async def emit_stage(self, objective_id: str, seq: int, engine: str,
                         capability: str, result: ExecuteResult,
                         prev_stage_urn: str = "",
                         concept_urn: str = "") -> str:
        """One member execution inside a composed run. Upstreams are the
        member's OWN emitted datasets (cross-platform provenance) plus the
        previous stage (the flow of the composition)."""
        urn = self.dataset_urn(f"stage.{objective_id}.{seq}-{engine}")
        if not self.enabled:
            return urn
        upstreams = list(result.provenance.datahub_urns)
        if prev_stage_urn:
            upstreams.append(prev_stage_urn)
        if concept_urn:
            upstreams.append(concept_urn)
        primitives = sorted({primitive_for(e.kind) for e in result.events})
        custom = {
            "objective_id": objective_id,
            "seq": seq,
            "engine": engine,
            "capability": capability,
            "status": result.status,
            "execution_id": result.provenance.ref.execution_id,
            "workflow_id": result.provenance.ref.workflow_id,
            "started_at": result.provenance.started_at,
            "finished_at": result.provenance.finished_at,
            "events": len(result.events),
            "primitives": ", ".join(primitives),
        }
        # Surface the stage's headline outputs as queryable properties.
        for key in ("session_id", "project_id", "product_name", "subject",
                    "files_written", "verification_passed", "build_ok"):
            if key in result.outputs:
                custom[f"out_{key}"] = result.outputs[key]
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                await self._ingest(
                    client, urn,
                    f"Composed-run stage {seq}: {capability} on {engine}",
                    custom, upstreams=upstreams or None)
        except httpx.HTTPError as e:
            self.status = f"stage emission failed: {e}"
        return urn

    async def emit_judgment(self, objective_id: str, judgment) -> str:
        """Publish one stage's gate decision as its own dataset.

        Verdicts live beside the work they judged, with each gate's determinism
        and evidence as queryable properties — so "why was this allowed to
        continue" is answerable from the catalog rather than from a log file.
        Upstream is the stage it judged, which puts the decision downstream of
        the work in the lineage graph, exactly where it belongs.
        """
        urn = self.dataset_urn(
            f"judgment.{objective_id}.{judgment.stage_seq}-{judgment.engine}")
        if not self.enabled:
            return urn
        custom: dict = {
            "objective_id": objective_id,
            "stage_seq": judgment.stage_seq,
            "engine": judgment.engine,
            "decision": judgment.action,
            "primitive": "Decision",
            "gates_total": len(judgment.verdicts),
            "gates_failed": len(judgment.failed),
        }
        for v in judgment.verdicts:
            custom[f"gate.{v.gate}"] = (
                f"{'pass' if v.passed else 'FAIL'} "
                f"[{v.determinism.value}] {v.evidence}")
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                await self._ingest(
                    client, urn,
                    f"Gate decision for stage {judgment.stage_seq} "
                    f"({judgment.engine}): {judgment.action}",
                    custom,
                    upstreams=[self.dataset_urn(
                        f"stage.{objective_id}.{judgment.stage_seq}-"
                        f"{judgment.engine}")])
        except httpx.HTTPError as e:
            self.status = f"judgment emission failed: {e}"
        return urn

    async def emit_objective(self, objective_id: str, title: str,
                             stage_urns: list[str], concept_urn: str,
                             engines_used: list[str], status: str,
                             workflow_id: str, started_at: str,
                             finished_at: str) -> str:
        urn = self.dataset_urn(f"objective.{objective_id}")
        if not self.enabled:
            return urn
        upstreams = list(stage_urns)
        if concept_urn:
            upstreams.append(concept_urn)
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                await self._ingest(
                    client, urn, f"Composed objective: {title}",
                    {
                        "objective_id": objective_id,
                        "title": title,
                        "status": status,
                        "engines_used": ", ".join(engines_used),
                        "stages": len(stage_urns),
                        "workflow_id": workflow_id,
                        "started_at": started_at,
                        "finished_at": finished_at,
                        "primitive": "Workflow",
                    },
                    upstreams=upstreams or None)
            self.status = f"emitted {urn} ← {len(upstreams)} upstreams"
        except httpx.HTTPError as e:
            self.status = f"objective emission failed: {e}"
        return urn
