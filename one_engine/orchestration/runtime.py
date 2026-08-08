"""Effectful runtime shared by BOTH orchestration paths.

The Temporal activities and the CompositeEngine's inline fallback execute
composed pipelines through exactly these functions — one narration, one
federation, one provenance shape, regardless of which orchestrator drives
the sequence. Temporal adds durability, retries, signals, and history on
top; it never changes what a stage IS.

Every function takes the pipeline explicitly rather than reaching for a
global registry, because pipelines belong to a composite, not to the process.
"""

from __future__ import annotations

from ..contract import (ArtifactRef, ComposableEngine, ExecuteRequest,
                        ExecuteResult, ExecutionRef, Provenance,
                        SemanticEvent, now_iso)
from ..events.bus import EventBus
from ..federation.datahub import FederationBridge
from .stages import ComposedPipeline, PlannedStage, concept_representations


async def start_objective(pipeline: ComposedPipeline, inputs: dict,
                          objective_id: str, orchestrator: str,
                          engine_name: str, bus: EventBus,
                          federation: FederationBridge) -> None:
    await federation.probe()
    await bus.publish(SemanticEvent(
        kind="ObjectiveStarted", engine=engine_name,
        subject=str(inputs.get("topic", "")), objective_id=objective_id,
        payload={"capability": pipeline.name, "inputs": inputs,
                 "orchestrator": orchestrator,
                 "stages": [f"{s.seq}:{s.engine}.{s.capability}"
                            for s in pipeline.stages]}))


async def run_and_record_stage(member: ComposableEngine, stage: PlannedStage,
                               objective_id: str, workflow_id: str,
                               objective_inputs: dict, acc: dict,
                               bus: EventBus, federation: FederationBridge,
                               prev_stage_urn: str, orchestrator: str,
                               engine_name: str
                               ) -> tuple[ExecuteResult, str]:
    """Execute one stage through the contract and record everything: the
    member's semantic events onto the unified bus, and the stage's cross-
    platform provenance into the DataHub federation. Returns the result and
    the federation stage URN (empty when DataHub is down — degraded, never
    fatal)."""
    req = ExecuteRequest(
        capability=stage.capability,
        inputs=stage.make_inputs(objective_inputs, acc),
        ref=ExecutionRef(objective_id=objective_id, workflow_id=workflow_id),
        timeout_s=stage.timeout_s)
    result = await member.execute(req)

    await bus.publish_all(result.events)
    stage_urn = await federation.emit_stage(
        objective_id, stage.seq,
        engine=result.provenance.engine or stage.engine,
        capability=stage.capability, result=result,
        prev_stage_urn=prev_stage_urn)
    await bus.publish(SemanticEvent(
        kind="StageCompleted", engine=engine_name, subject=stage_urn,
        objective_id=objective_id,
        payload={"seq": stage.seq, "engine": stage.engine,
                 "capability": stage.capability, "status": result.status,
                 "orchestrator": orchestrator}))
    return result, stage_urn


async def finalize_and_assemble(pipeline: ComposedPipeline, inputs: dict,
                                objective_id: str, workflow_id: str,
                                orchestrator: str, engine_name: str,
                                stage_results: list[ExecuteResult],
                                stage_urns: list[str], started_at: str,
                                bus: EventBus,
                                federation: FederationBridge) -> ExecuteResult:
    """Close a composed run: emit cross-domain identity (the concept) and the
    objective dataset to the federation, narrate completion, and assemble the
    contract-shaped result whose provenance nests every stage."""
    topic = str(inputs.get("topic", "")).strip()

    acc: dict[str, dict] = {}
    status, error = "completed", ""
    for stage, result in zip(pipeline.stages, stage_results):
        if result.status == "completed":
            acc[stage.engine] = result.outputs
        else:
            status = "failed"
            error = (f"stage {stage.seq} ({stage.capability}) failed: "
                     f"{result.error}")
            break
    if len(stage_results) < len(pipeline.stages) and not error:
        status = "failed"
        error = (f"pipeline stopped after {len(stage_results)} of "
                 f"{len(pipeline.stages)} stages")

    concept_urn = ""
    if topic and acc:
        first_urns = (stage_results[0].provenance.datahub_urns
                      if stage_results else [])
        concept_urn = await federation.emit_concept(
            topic, concept_representations(topic, acc),
            born_in=first_urns[0] if first_urns else "")
    objective_urn = await federation.emit_objective(
        objective_id, title=f"{pipeline.name}: {topic}",
        stage_urns=stage_urns, concept_urn=concept_urn,
        engines_used=[r.provenance.engine for r in stage_results],
        status=status, workflow_id=workflow_id, started_at=started_at,
        finished_at=now_iso())
    await bus.publish(SemanticEvent(
        kind="ObjectiveCompleted", engine=engine_name,
        subject=objective_urn, objective_id=objective_id,
        payload={"capability": pipeline.name, "status": status,
                 "stages_completed": len(stage_results),
                 "orchestrator": orchestrator,
                 "datahub": federation.status}))

    artifacts: list[ArtifactRef] = []
    for r in stage_results:
        artifacts.extend(r.artifacts)
    outputs = {
        "objective_id": objective_id,
        "topic": topic,
        "status": status,
        "stages": [{"seq": s.seq, "engine": s.engine,
                    "capability": s.capability,
                    "outputs": acc.get(s.engine, {})}
                   for s in pipeline.stages],
        "concept_urn": concept_urn,
        "objective_urn": objective_urn,
    }
    return ExecuteResult(
        status=status, outputs=outputs, artifacts=artifacts, error=error,
        provenance=Provenance(
            engine=engine_name, capability=pipeline.name,
            ref=ExecutionRef(objective_id=objective_id,
                             workflow_id=workflow_id),
            started_at=started_at, finished_at=now_iso(),
            datahub_urns=[objective_urn] if objective_urn else [],
            notes=[f"orchestrator: {orchestrator}"],
            children=[r.provenance for r in stage_results]))
