"""The Temporal worker — where durable orchestration meets the contract.

Activities are bound methods on ObjectiveActivities, so they close over the
live member RemoteEngines, the event bus, and the federation bridge. The
workflow stays pure and deterministic; every effect (HTTP to an engine,
DataHub ingest, event append) happens here.

Run it with:  python -m one_engine.orchestration.worker
"""

from __future__ import annotations

import asyncio

from temporalio import activity
from temporalio.client import Client
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.worker import Worker

from ..config import SystemConfig, load_config
from ..contract import ComposableEngine, ExecuteResult, Provenance
from ..events.bus import EventBus
from ..federation.datahub import FederationBridge
from ..remote import RemoteEngine
from ..scaffold import StageJudgment
from .runtime import finalize_and_assemble, record_judgment, run_and_record_stage, start_objective
from .stages import COMPOSED_PIPELINES, Registry, StageOutcome
from .workflows import (
    FINALIZE_ACTIVITY,
    JUDGMENT_ACTIVITY,
    STAGE_ACTIVITY,
    START_ACTIVITY,
    ComposedObjectiveWorkflow,
)


class ObjectiveActivities:
    """Activities bound to the live composition: member engines addressed
    through the contract, the unified event bus, and the federation bridge.
    `engine_name` is whose narration these events carry — the composite's,
    since the composite is what the objective belongs to."""

    def __init__(self, members: dict[str, ComposableEngine], bus: EventBus,
                 federation: FederationBridge, engine_name: str,
                 pipelines: Registry | None = None):
        self.members = members
        self.bus = bus
        self.federation = federation
        self.engine_name = engine_name
        self.pipelines: Registry = (COMPOSED_PIPELINES if pipelines is None
                                    else pipelines)
        self._assert_workflow_agrees()

    def _assert_workflow_agrees(self) -> None:
        """The workflow resolves pipelines from the MODULE registry; these
        activities may be handed a different one. They must agree on the stage
        list, or the workflow will ask for a stage the activities cannot find
        — as a KeyError, mid-run, after real work has already happened.

        Only the stage identities are compared. Timeouts, gates, and input
        builders legitimately differ (a test may tighten a budget); the
        sequence of (seq, engine, capability) may not.
        """
        def shape(pipeline) -> list[tuple[int, str, str]]:
            return [(s.seq, s.engine, s.capability) for s in pipeline.stages]

        for name, pipeline in self.pipelines.items():
            canonical = COMPOSED_PIPELINES.get(name)
            if canonical is None:
                raise ValueError(
                    f"pipeline {name!r} is unknown to the workflow, which "
                    f"resolves from one_engine.orchestration.stages."
                    f"COMPOSED_PIPELINES. Register it there too.")
            if shape(pipeline) != shape(canonical):
                raise ValueError(
                    f"pipeline {name!r} disagrees with the workflow's copy:\n"
                    f"  activities: {shape(pipeline)}\n"
                    f"  workflow:   {shape(canonical)}")

    @activity.defn(name=START_ACTIVITY)
    async def start_objective(self, capability: str, inputs: dict,
                              objective_id: str,
                              orchestrator: str) -> dict[str, dict]:
        # Returns the prepared `acc` seed (impact analysis, for pipelines
        # that declare it) so the workflow can decide what to skip.
        return await start_objective(
            self.pipelines[capability], inputs, objective_id, orchestrator,
            self.engine_name, self.bus, self.federation)

    @activity.defn(name=STAGE_ACTIVITY)
    async def run_stage(self, capability: str, seq: int, objective_id: str,
                        workflow_id: str, inputs: dict, acc: dict,
                        prev_stage_urn: str) -> StageOutcome:
        # Activities receive (pipeline, seq) rather than a serialized stage:
        # a stage carries a callable that must never cross a process
        # boundary, so the pipeline declaration stays the source of truth.
        stage = self.pipelines[capability].stage_by_seq(seq)
        member = self.members.get(stage.engine)
        if member is None:
            # A missing member is a configuration fault, not a transient one:
            # return a failed result rather than raising, so the workflow
            # records it and finalizes honestly instead of retrying forever.
            return StageOutcome(result=ExecuteResult(
                status="failed", error=f"missing member {stage.engine!r}",
                provenance=Provenance(engine=stage.engine,
                                      capability=stage.capability)))
        result, stage_urn = await run_and_record_stage(
            member, stage, objective_id, workflow_id, inputs, acc,
            self.bus, self.federation, prev_stage_urn, "temporal",
            self.engine_name)
        return StageOutcome(result=result, stage_urn=stage_urn)

    @activity.defn(name=JUDGMENT_ACTIVITY)
    async def record_judgment(self, objective_id: str,
                              judgment: StageJudgment) -> None:
        # The decision was already made, deterministically, in the workflow.
        # This activity only records it — publishing the verdict as a fact and
        # as DataHub provenance.
        await record_judgment(objective_id, judgment, self.engine_name,
                              self.bus, self.federation)

    @activity.defn(name=FINALIZE_ACTIVITY)
    async def finalize_objective(self, capability: str, inputs: dict,
                                 objective_id: str, workflow_id: str,
                                 orchestrator: str,
                                 stage_results: list[ExecuteResult],
                                 stage_urns: list[str],
                                 started_at: str) -> ExecuteResult:
        return await finalize_and_assemble(
            self.pipelines[capability], inputs, objective_id, workflow_id,
            orchestrator, self.engine_name, stage_results, stage_urns,
            started_at, self.bus, self.federation)


def build_members(cfg: SystemConfig) -> dict[str, ComposableEngine]:
    """Members are addressed by URL — the worker consumes them through the
    same contract the composite does, and equally cannot see inside them."""
    return {name: RemoteEngine(m.url) for name, m in cfg.engines.items()}


async def connect(cfg: SystemConfig) -> Client:
    return await Client.connect(cfg.temporal_address,
                                namespace=cfg.temporal_namespace,
                                data_converter=pydantic_data_converter)


async def main() -> None:
    cfg = load_config()
    members = build_members(cfg)
    bus = EventBus(cfg.events_log_path)
    federation = FederationBridge(cfg.datahub_gms, cfg.unified_platform,
                                  cfg.datahub_env)
    await federation.probe()
    client = await connect(cfg)
    acts = ObjectiveActivities(members, bus, federation,
                               engine_name=cfg.unified_name)
    worker = Worker(client, task_queue=cfg.temporal_task_queue,
                    workflows=[ComposedObjectiveWorkflow],
                    activities=[acts.start_objective, acts.run_stage,
                                acts.record_judgment,
                                acts.finalize_objective])
    print(f"[worker] task queue: {cfg.temporal_task_queue} | "
          f"members: {', '.join(members)} | datahub: {federation.status}")
    try:
        await worker.run()
    finally:
        for m in members.values():
            await m.aclose()


if __name__ == "__main__":
    asyncio.run(main())
