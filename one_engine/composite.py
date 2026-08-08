"""CompositeEngine — many engines behind one Universal Engine Contract.

This is the unified system AND the recursion proof, in one class:

  * it CONSUMES members through the contract (usually RemoteEngines pointing
    at adapter servers — it cannot tell, and must never need to tell, what a
    member contains);
  * it EXPOSES the same contract itself, so anything that can consume a leaf
    can consume this composite — including another CompositeEngine.

Atomic member capabilities pass through with provenance wrapped one level
deeper. Composed capabilities run multi-engine pipelines: durably through
Temporal when a workflow launcher is wired in, inline otherwise (degraded but
honest — the orchestrator used is recorded in provenance).
"""

from __future__ import annotations

import asyncio
from typing import Awaitable, Callable

from .contract import (CapabilitySpec, ComposableEngine, CompositionNode,
                       ContextDescriptor, EngineIdentity, EngineManifest,
                       ExecuteRequest, ExecuteResult, FieldSpec,
                       HealthReport, KnowledgeDescriptor, Provenance,
                       SemanticEvent, StateSnapshot, now_iso)
from .events.bus import EventBus
from .federation.datahub import FederationBridge
from .orchestration.runtime import (finalize_and_assemble,
                                    run_and_record_stage, start_objective)
from .orchestration.stages import (COMPOSED_PIPELINES, Registry,
                                   new_objective_id)

# Temporal path, injected by the app when the cluster is reachable:
# (capability, inputs, objective_id) → ExecuteResult.
WorkflowLauncher = Callable[[str, dict, str], Awaitable[ExecuteResult]]


class CompositeEngine:
    def __init__(self, name: str, members: dict[str, ComposableEngine],
                 bus: EventBus, federation: FederationBridge,
                 description: str = "", datahub_platform: str = "one-engine",
                 workflow_launcher: WorkflowLauncher | None = None,
                 pipelines: Registry | None = None):
        self.name = name
        self.description = description or (
            "Unified intelligence composed of autonomous engines. Exposes "
            "the same contract it consumes, so it can itself be composed.")
        self.members = members
        self.bus = bus
        self.federation = federation
        self.datahub_platform = datahub_platform
        self.workflow_launcher = workflow_launcher
        # Pipelines this composite OWNS. A member's composed capability is
        # not in here — it is consumed as an ordinary capability, which is
        # what lets composition nest more than one level deep.
        self.pipelines: Registry = (COMPOSED_PIPELINES if pipelines is None
                                    else pipelines)
        self._routing: dict[str, str] = {}      # capability → member key
        self._executions_total = 0
        self._active: set[str] = set()
        self._counters: dict[str, int] = {}

    # ----------------------------------------------------------------- #
    # description / self-description
    # ----------------------------------------------------------------- #
    def _composed_specs(self) -> list[CapabilitySpec]:
        return [p.spec(self.name) for p in self.pipelines.values()]

    async def _member_manifests(self) -> dict[str, EngineManifest]:
        keys = list(self.members)
        manifests = await asyncio.gather(
            *(self.members[k].describe() for k in keys),
            return_exceptions=True)
        out: dict[str, EngineManifest] = {}
        for k, m in zip(keys, manifests):
            if isinstance(m, EngineManifest):
                out[k] = m
        return out

    async def describe(self) -> EngineManifest:
        manifests = await self._member_manifests()
        capabilities: list[CapabilitySpec] = []
        events: set[str] = {"ObjectiveStarted", "StageCompleted",
                            "ObjectiveCompleted"}
        children: list[CompositionNode] = []
        for key, m in manifests.items():
            children.append(m.identity.composition
                            or CompositionNode(name=m.identity.name,
                                               kind=m.identity.kind))
            events.update(m.events_emitted)
            for cap in m.capabilities:
                cap = cap.model_copy()
                # Opacity at the boundary: the composite serves these as ITS
                # capabilities. The true execution path lives in provenance,
                # where transparency belongs.
                cap.engine = self.name
                capabilities.append(cap)
        capabilities.extend(self._composed_specs())
        self._routing = {cap.name: key
                         for key, m in manifests.items()
                         for cap in m.capabilities}
        return EngineManifest(
            identity=EngineIdentity(
                name=self.name, description=self.description,
                kind="composite", datahub_platform=self.datahub_platform,
                composition=CompositionNode(
                    name=self.name, kind="composite",
                    summary=self.description, members=children)),
            capabilities=capabilities,
            events_emitted=sorted(events),
            workflows=sorted(self.pipelines))

    # ----------------------------------------------------------------- #
    # execution
    # ----------------------------------------------------------------- #
    async def execute(self, req: ExecuteRequest) -> ExecuteResult:
        self._executions_total += 1
        self._counters[req.capability] = \
            self._counters.get(req.capability, 0) + 1
        self._active.add(req.ref.execution_id)
        try:
            # Only pipelines this composite DECLARES are run as compositions.
            # A member's composed capability falls through to the atomic
            # path and is delegated whole — that is exactly how a system
            # becomes a capability inside a larger system.
            if req.capability in self.pipelines:
                return await self._execute_composed(req)
            return await self._execute_atomic(req)
        finally:
            self._active.discard(req.ref.execution_id)

    async def _find_member(self, capability: str) -> tuple[str, ComposableEngine] | None:
        if capability not in self._routing:
            await self.describe()            # refresh routing from live members
        key = self._routing.get(capability)
        return (key, self.members[key]) if key else None

    async def _execute_atomic(self, req: ExecuteRequest) -> ExecuteResult:
        found = await self._find_member(req.capability)
        if not found:
            return ExecuteResult(
                status="failed",
                error=f"no member offers capability {req.capability!r}",
                provenance=Provenance(engine=self.name,
                                      capability=req.capability, ref=req.ref))
        _, member = found
        started = now_iso()
        child_req = ExecuteRequest(
            capability=req.capability, inputs=req.inputs,
            ref=req.ref.model_copy(update={
                "execution_id": f"{req.ref.execution_id}.0",
                "parent_execution_id": req.ref.execution_id}),
            timeout_s=req.timeout_s)
        result = await member.execute(child_req)
        # The unified system narrates everything its members did.
        await self.bus.publish_all(result.events)
        return ExecuteResult(
            status=result.status, outputs=result.outputs,
            artifacts=result.artifacts, events=result.events,
            error=result.error,
            provenance=Provenance(
                engine=self.name, capability=req.capability, ref=req.ref,
                started_at=started, finished_at=now_iso(),
                datahub_urns=result.provenance.datahub_urns,
                children=[result.provenance]))

    async def _execute_composed(self, req: ExecuteRequest) -> ExecuteResult:
        """Composed pipelines prefer the durable path. Inline execution is
        the honest fallback, and provenance always names which one ran."""
        objective_id = req.ref.objective_id or new_objective_id()
        if self.workflow_launcher is not None:
            return await self.workflow_launcher(req.capability, req.inputs,
                                                objective_id)
        return await self.run_pipeline_inline(req.capability, req.inputs,
                                              objective_id)

    async def run_pipeline_inline(self, capability: str, inputs: dict,
                                  objective_id: str,
                                  workflow_id: str = "",
                                  orchestrator: str = "inline") -> ExecuteResult:
        """The composed pipeline, stage by stage, through the shared runtime.

        The Temporal worker drives the same runtime functions from inside
        activities; this inline form exists so the system degrades to direct
        composition rather than refusing when the orchestrator is down. The
        orchestrator that ran is always named in provenance.
        """
        pipeline = self.pipelines[capability]
        started = now_iso()
        await start_objective(pipeline, inputs, objective_id, orchestrator,
                              self.name, self.bus, self.federation)

        acc: dict[str, dict] = {}
        results: list[ExecuteResult] = []
        stage_urns: list[str] = []
        prev_urn = ""
        for stage in pipeline.stages:
            member = self.members.get(stage.engine)
            if member is None:
                results.append(ExecuteResult(
                    status="failed",
                    error=f"missing member {stage.engine!r}",
                    provenance=Provenance(engine=stage.engine,
                                          capability=stage.capability)))
                break
            result, stage_urn = await run_and_record_stage(
                member, stage, objective_id, workflow_id, inputs, acc,
                self.bus, self.federation, prev_urn, orchestrator, self.name)
            results.append(result)
            if stage_urn:
                stage_urns.append(stage_urn)
                prev_urn = stage_urn
            if result.status != "completed":
                break
            acc[stage.engine] = result.outputs

        return await finalize_and_assemble(
            pipeline, inputs, objective_id, workflow_id, orchestrator,
            self.name, results, stage_urns, started, self.bus,
            self.federation)

    # ----------------------------------------------------------------- #
    # observability
    # ----------------------------------------------------------------- #
    async def health(self) -> HealthReport:
        """Honest health: the system is 'ok' only when it can deliver what
        the architecture promises. Members doing work is necessary but not
        sufficient — without DataHub there is no provenance, and without
        Temporal there is no durability across a restart. Both are core
        promises, so their absence reads as degraded rather than fine."""
        keys = list(self.members)
        results = await asyncio.gather(
            *(self.members[k].health() for k in keys),
            return_exceptions=True)
        checks: dict[str, str] = {}
        status = "ok"
        reachable = 0
        for k, r in zip(keys, results):
            if isinstance(r, HealthReport):
                checks[f"member:{k}"] = r.status
                reachable += 1
                if r.status != "ok":
                    status = "degraded"
            else:
                checks[f"member:{k}"] = f"unreachable ({type(r).__name__})"
                status = "degraded"

        await self.federation.probe()
        checks["datahub_federation"] = self.federation.status
        if not self.federation.enabled:
            status = "degraded"
        checks["orchestrator"] = ("temporal (durable)" if self.workflow_launcher
                                  else "inline (degraded: no durable "
                                       "execution, retries, or human gates)")
        if self.workflow_launcher is None:
            status = "degraded"

        # No member answering at all is not degradation, it is absence: the
        # composite has nothing to compose.
        if keys and reachable == 0:
            status = "down"
        return HealthReport(engine=self.name, status=status, checks=checks)

    async def state(self) -> StateSnapshot:
        events = self.bus.recent(limit=10000)
        return StateSnapshot(
            engine=self.name, active_executions=sorted(self._active),
            executions_total=self._executions_total,
            events_total=len(events),
            last_event_ts=events[-1].ts if events else "",
            counters=dict(self._counters))

    async def context(self) -> ContextDescriptor:
        """The composite's context is its objectives — what the system has
        been asked to achieve, across every engine."""
        recent: list[dict] = []
        for e in self.bus.recent(limit=2000):
            if e.kind == "ObjectiveStarted":
                recent.append({"objective_id": e.objective_id,
                               "subject": e.subject, "started": e.ts,
                               "status": "running"})
            elif e.kind == "ObjectiveCompleted":
                for r in recent:
                    if r["objective_id"] == e.objective_id:
                        r["status"] = e.payload.get("status", "completed")
                        r["finished"] = e.ts
        return ContextDescriptor(
            engine=self.name, description=self.description,
            recent=recent[-20:],
            stats={"objectives": len(recent)})

    async def knowledge(self) -> KnowledgeDescriptor:
        keys = list(self.members)
        results = await asyncio.gather(
            *(self.members[k].knowledge() for k in keys),
            return_exceptions=True)
        stores = [{"engine": self.name,
                   "datahub_platform": self.datahub_platform,
                   "holds": "cross-domain objectives, stages, concepts"}]
        for k, r in zip(keys, results):
            if isinstance(r, KnowledgeDescriptor):
                stores.append({"engine": r.engine,
                               "datahub_platform": r.datahub_platform,
                               "description": r.description})
        return KnowledgeDescriptor(
            engine=self.name,
            description="Federated knowledge: each member keeps its own "
                        "domain graph and DataHub platform; the composite "
                        "owns only cross-domain identity and provenance.",
            datahub_platform=self.datahub_platform, stores=stores)

    async def recent_events(self, since_id: str = "") -> list[SemanticEvent]:
        return self.bus.recent(since_id)

    async def ingest_event(self, event: SemanticEvent) -> None:
        # External facts join the unified narration; nothing dispatches.
        await self.bus.publish(event)

    async def aclose(self) -> None:
        await asyncio.gather(*(m.aclose() for m in self.members.values()),
                             return_exceptions=True)
