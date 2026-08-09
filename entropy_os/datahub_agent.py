"""An agent that consults the graph, builds, and puts the verdict back.

Three steps, and the middle one is the only one anybody usually builds:

    READ    ask DataHub what already exists — real datasets, the fields they
            actually carry, what feeds them — through DataHub's own MCP server
    ACT     generate a service against those fields, through the Universal
            Engine Contract, so the existing hard gates rule on it unchanged
    WRITE   publish the result back: the generated project as a dataset, an
            UpstreamLineage edge from every dataset that informed it, and each
            gate verdict as a DataHub assertion

The point of the third step is that the next agent inherits it. A run that
generated something and told nobody has produced an artifact; a run that
recorded what it made, what it was made FROM, and whether it passed has
produced knowledge. The graph is the difference.

**What the agent will not do.** If DataHub could not be consulted, it says so
in the request it sends onward, and the provenance it writes back records that
the build was ungrounded. Generating against a guess is allowed; generating
against a guess and calling it schema-aware is not, and only the second one
requires lying.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from . import engine_client
from .composition.contract import Determinism, Verdict
from .datahub_read import GraphContext, consult
from .schema_fidelity import Fidelity, measure
from .schema_fidelity import verdict as fidelity_verdict
from .vending import Acceptance, decide

DEFAULT_GMS = "http://localhost:8080"
PLATFORM = "entropy-agent"
ENV = "PROD"

# Long enough for a real generation, which is minutes of model work.
BUILD_TIMEOUT_S = 1800.0

# Split point between the human request and the catalog's own words. Shared
# with the software engine, which extracts everything after it verbatim.
CATALOG_MARKER = "--- CATALOG SCHEMA ---"


def dataset_urn(name: str, platform: str = PLATFORM, env: str = ENV) -> str:
    return f"urn:li:dataset:(urn:li:dataPlatform:{platform},{name},{env})"


@dataclass
class AgentRun:
    """One full read → act → write cycle, and what is true about it."""
    request: str
    graph: GraphContext
    grounded: bool                       # did real schema information reach the build
    outputs: dict[str, Any] = field(default_factory=dict)
    verdicts: list[Verdict] = field(default_factory=list)
    fidelity: Fidelity | None = None
    acceptance: Acceptance | None = None
    urn: str = ""
    upstreams: list[str] = field(default_factory=list)
    published: str = ""                  # what the write-back actually managed
    error: str = ""

    def summary(self) -> str:
        acc = self.acceptance
        return (f"{'grounded' if self.grounded else 'UNGROUNDED'} build · "
                f"{len(self.graph.datasets)} dataset(s) consulted · "
                f"{'accepted' if acc and acc.accepted else 'not accepted'}"
                f" ({acc.reason if acc else self.error or 'no verdict'})")


def compose_request(request: str, graph: GraphContext) -> str:
    """The request the generator actually receives.

    The graph is pasted in as plain field paths and types rather than
    summarised, because a summary is a place for a model to introduce a field
    nobody has. When the graph could not be consulted the request says so in
    the same breath — the generator is told it is working blind rather than
    left to assume it is not.
    """
    if not graph.consulted:
        return (f"{request}\n\n"
                f"NOTE: the metadata catalog could not be consulted "
                f"({graph.reason}). No real schema was available, so infer the "
                f"data model from the request alone and keep it minimal.")
    if not graph.datasets:
        return (f"{request}\n\n"
                f"NOTE: the metadata catalog was consulted and holds nothing "
                f"related to this request. Infer the data model from the "
                f"request alone.")
    # The marker is machine-readable on purpose. The engine splits on it to
    # carry these field names, verbatim, into the phase that actually decides
    # the data model — prose alone reached intent and died there.
    return (
        f"{request}\n\n"
        f"Use these REAL datasets from the organisation's metadata catalog. "
        f"Model your schema on their actual fields — do not invent columns, "
        f"and do not rename the ones given:\n\n"
        f"{CATALOG_MARKER}\n{graph.brief()}")


class Publisher:
    """Writes the run back into DataHub over the classic restli endpoint.

    Plain httpx, matching the engines' own bridges: the acryl SDK does not
    install on the interpreter this runs under, and a metadata write is a
    POST with a JSON body — a dependency that cannot be installed is a worse
    trade than fifteen lines of request building.
    """

    def __init__(self, gms_url: str = ""):
        self.gms = (gms_url or os.environ.get("DATAHUB_GMS", DEFAULT_GMS)).rstrip("/")
        self.enabled = False
        self.status = "not probed"

    async def probe(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5.0) as c:
                r = await c.get(f"{self.gms}/health")
            self.enabled = r.status_code == 200
        except httpx.HTTPError as e:
            self.enabled = False
            self.status = f"GMS unreachable at {self.gms}: {type(e).__name__}"
            return False
        self.status = f"live → {self.gms}" if self.enabled else f"GMS not healthy at {self.gms}"
        return self.enabled

    async def _ingest(self, client: httpx.AsyncClient, snapshot: dict) -> None:
        """The legacy snapshot path. Datasets still accept it."""
        r = await client.post(f"{self.gms}/entities?action=ingest", json=snapshot,
                              headers={"X-RestLi-Protocol-Version": "2.0.0"})
        r.raise_for_status()

    async def _propose(self, client: httpx.AsyncClient, entity_type: str,
                       urn: str, aspect_name: str, aspect: dict) -> None:
        """One aspect, through the proposal API.

        Assertions are not ingestable as snapshots on this GMS — the snapshot
        endpoint answers 400 for them, because snapshots predate the entity.
        Datasets work either way; assertions only work here. Found by trying
        both against the running instance rather than by reading which was
        canonical.
        """
        r = await client.post(
            f"{self.gms}/aspects?action=ingestProposal",
            json={"proposal": {
                "entityType": entity_type, "entityUrn": urn,
                "changeType": "UPSERT", "aspectName": aspect_name,
                "aspect": {"value": json.dumps(aspect),
                           "contentType": "application/json"}}},
            headers={"X-RestLi-Protocol-Version": "2.0.0"})
        r.raise_for_status()

    async def dataset(self, client: httpx.AsyncClient, urn: str, description: str,
                      props: dict[str, Any], upstreams: list[str]) -> None:
        aspects: list[dict] = [{
            "com.linkedin.dataset.DatasetProperties": {
                "description": description[:900],
                "customProperties": {k: str(v)[:400] for k, v in props.items()},
            }
        }]
        if upstreams:
            # The edge that makes this generated artifact traceable to the
            # datasets it was generated FROM. Without it the code is in the
            # catalog but its grounding is not.
            aspects.append({
                "com.linkedin.dataset.UpstreamLineage": {
                    "upstreams": [{"dataset": u, "type": "TRANSFORMED"}
                                  for u in upstreams]
                }
            })
        await self._ingest(client, {"entity": {"value": {
            "com.linkedin.metadata.snapshot.DatasetSnapshot": {
                "urn": urn, "aspects": aspects}}}})

    async def assertion(self, client: httpx.AsyncClient, subject_urn: str,
                        verdict: Verdict, seq: int, run_id: str) -> str:
        """One gate verdict, as an assertion with a RESULT.

        Two aspects, because one is not enough to be useful. AssertionInfo
        says what was checked; AssertionRunEvent says how it came out. Without
        the second, DataHub shows an assertion that exists and never ran —
        which is exactly the "recorded but not run" state the demo counts
        separately, and not what happened here.

        The shape is the one veritas already emits successfully into this
        instance (customAssertion, not datasetAssertion). Inventing a second
        shape for the same idea is how two emitters end up disagreeing about
        what a verdict looks like.
        """
        name = subject_urn.split(",")[1] if "," in subject_urn else subject_urn
        assertion_urn = f"urn:li:assertion:entropy-{name}-{seq}"
        kind = (verdict.determinism.value if hasattr(verdict.determinism, "value")
                else str(verdict.determinism))
        await self._propose(client, "assertion", assertion_urn, "assertionInfo", {
            "type": "CUSTOM",
            "customAssertion": {
                "type": "ENTROPY_GATE",
                "entity": subject_urn,
                # The determinism travels with the verdict: a green mark from
                # pytest and one from a judge model are different claims, and
                # a reader sees only this line.
                "logic": f"[{kind}] {verdict.gate}: {verdict.evidence[:280]}",
            },
            "description": (f"Entropy gate verdict — {verdict.gate} ({kind}): "
                            f"{'passed' if verdict.passed else 'FAILED'}"),
        })
        await self._propose(client, "assertion", assertion_urn, "assertionRunEvent", {
            "timestampMillis": int(time.time() * 1000),
            "runId": run_id,
            "assertionUrn": assertion_urn,
            "asserteeUrn": subject_urn,
            "status": "COMPLETE",
            "result": {
                "type": "SUCCESS" if verdict.passed else "FAILURE",
                "nativeResults": {"gate": verdict.gate, "determinism": kind},
            },
        })
        return assertion_urn

    async def publish(self, run: AgentRun) -> str:
        if not await self.probe():
            return self.status
        name = f"generated.{run.outputs.get('project_id', 'unknown')}"
        run.urn = dataset_urn(name)
        run.upstreams = [d.urn for d in run.graph.datasets]
        acc = run.acceptance
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                await self.dataset(
                    client, run.urn,
                    f"Generated by the Entropy metadata-aware agent from: {run.request[:200]}",
                    {
                        "request": run.request[:400],
                        "grounded_in_catalog": run.grounded,
                        "datasets_consulted": len(run.graph.datasets),
                        "accepted": bool(acc and acc.accepted),
                        "acceptance_reason": acc.reason if acc else "",
                        "hard_gates_passed": acc.hard_passed if acc else 0,
                        "hard_gates_failed": acc.hard_failed if acc else 0,
                        "product_name": run.outputs.get("product_name", ""),
                        "files_written": run.outputs.get("files_written", 0),
                        "catalog_fields_adopted": (
                            f"{len(run.fidelity.matched)}/"
                            f"{len(run.fidelity.catalog_fields - {'id', 'created_at'})}"
                            if run.fidelity else "not measured"),
                        "out_dir": run.outputs.get("out_dir", ""),
                    },
                    run.upstreams)
                run_id = f"entropy-{run.outputs.get('project_id', 'run')}"
                written = [await self.assertion(client, run.urn, v, i, run_id)
                           for i, v in enumerate(run.verdicts)]
        except httpx.HTTPError as e:
            return f"write-back failed: {type(e).__name__}: {e}"
        return (f"published {run.urn} with {len(written)} assertion(s) "
                f"and {len(run.upstreams)} lineage upstream(s)")


async def run(request: str, gms_url: str = "", out_dir: str = "") -> AgentRun:
    """Read the graph, build against it, write the verdict back."""
    graph = await consult(request, gms_url=gms_url)
    grounded = graph.consulted and any(d.is_described for d in graph.datasets)
    r = AgentRun(request=request, graph=graph, grounded=grounded)

    inputs: dict[str, Any] = {"request": compose_request(request, graph)}
    if out_dir:
        inputs["out_dir"] = out_dir
    try:
        result = await engine_client.execute("software.build", inputs,
                                             timeout_s=BUILD_TIMEOUT_S)
    except engine_client.EngineUnreachable as e:
        r.error = f"the engine is not reachable: {e}"
        return r

    r.outputs = result.get("outputs") or {}
    r.verdicts = [Verdict.model_validate(v) for v in result.get("verdicts", [])]

    # The agent's own verdict on its own claim. The engine gates the code;
    # nothing gated whether the code actually adopted the schema the agent
    # went and fetched, which is the one thing that makes this build
    # metadata-aware rather than metadata-adjacent. Only meaningful when a
    # schema was available: there is no fidelity to measure against a catalog
    # that offered no fields, and a gate that fired anyway would be scoring
    # the weather.
    catalog_fields = {f.path for d in graph.datasets for f in d.fields if f.path}
    out_path = r.outputs.get("out_dir")
    if catalog_fields and out_path:
        r.fidelity = measure(out_path, catalog_fields)
        r.verdicts.append(fidelity_verdict(r.fidelity))
    r.acceptance = decide(result.get("status", "failed"), r.verdicts,
                          result.get("error", ""))
    r.published = await Publisher(gms_url).publish(r)
    return r


__all__ = ["AgentRun", "Publisher", "Determinism", "compose_request",
           "dataset_urn", "run"]
