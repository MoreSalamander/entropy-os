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

import asyncio

from ..contract import (
    ArtifactRef,
    ComposableEngine,
    ExecuteRequest,
    ExecuteResult,
    ExecutionRef,
    Provenance,
    SemanticEvent,
    Verdict,
    identifying,
    now_iso,
)
from ..events.bus import EventBus
from ..federation import impact
from ..federation.datahub import FederationBridge
from ..scaffold import StageJudgment
from .stages import PREPARED_KEY, ComposedPipeline, PlannedStage, concept_representations

# How often a running stage is asked what it has learned so far. Engine work
# is measured in minutes, so this is cheap; the point is that a long stage is
# visible while it runs rather than only once it returns.
EVENT_POLL_INTERVAL_S = 3.0


async def _stream_member_events(member: ComposableEngine, bus: EventBus,
                                objective_id: str, seen: set[str],
                                stop: asyncio.Event) -> None:
    """Forward a member's semantic events onto the unified bus WHILE it works.

    This is the contract's GET /events route used for exactly what it is for:
    an engine narrating facts as they happen, without the composite reaching
    inside it. Failures are swallowed — losing progress narration must never
    disturb the execution it is narrating.
    """
    since = ""
    while not stop.is_set():
        try:
            for event in await member.recent_events(since):
                since = event.event_id
                # Other objectives may share this engine; only this run's
                # facts belong in this objective's narration.
                if event.objective_id != objective_id:
                    continue
                if event.event_id not in seen:
                    seen.add(event.event_id)
                    await bus.publish(event)
        except Exception:
            pass
        try:
            await asyncio.wait_for(stop.wait(), timeout=EVENT_POLL_INTERVAL_S)
        except TimeoutError:
            continue


async def start_objective(pipeline: ComposedPipeline, inputs: dict,
                          objective_id: str, orchestrator: str,
                          engine_name: str, bus: EventBus,
                          federation: FederationBridge) -> dict:
    """Open an objective and gather whatever context its pipeline needs before
    any stage runs. Returns the prepared `acc` seed — for an evolving
    pipeline, the impact report that decides which stages are worth running.
    """
    await federation.probe()
    subject = str(inputs.get("topic", ""))
    prepared: dict = {}

    if pipeline.prepare == "impact":
        report = impact.analyze(subject, bus)
        prepared = {"impact": report.to_dict()}
        await bus.publish(SemanticEvent(
            kind="ImpactAnalyzed", engine=engine_name, subject=subject,
            objective_id=objective_id,
            payload={"concept_slug": report.concept_slug,
                     "prior_objectives": report.prior_objectives,
                     "affected": sorted(report.affected),
                     "unaffected": report.unaffected,
                     "is_new_subject": report.is_new_subject}))

    await bus.publish(SemanticEvent(
        kind="ObjectiveStarted", engine=engine_name,
        subject=subject, objective_id=objective_id,
        payload={"capability": pipeline.name, "inputs": inputs,
                 "orchestrator": orchestrator,
                 "stages": [f"{s.seq}:{s.engine}.{s.capability}"
                            for s in pipeline.stages]}))
    return {PREPARED_KEY: prepared} if prepared else {}


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

    # Narrate the stage while it runs, then publish whatever the streamer did
    # not already catch — deduplicated by event id, so a stage that finishes
    # between polls still contributes every fact exactly once.
    seen: set[str] = set()
    stop = asyncio.Event()
    streamer = asyncio.create_task(
        _stream_member_events(member, bus, objective_id, seen, stop))
    try:
        result = await member.execute(req)
    finally:
        stop.set()
        await streamer

    await bus.publish_all([e for e in result.events
                           if e.event_id not in seen])
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
                 "orchestrator": orchestrator,
                 # The handles by which a later run can find this work. This
                 # is what makes the event log sufficient for impact
                 # analysis, without reading any engine's private vocabulary.
                 "produced": identifying(result.outputs),
                 # Where the work actually landed. Without this the refs live
                 # only in this process's memory and die with it — which is
                 # exactly what happened to the earliest runs, leaving their
                 # outputs findable only by guessing at each engine's naming
                 # convention. A path recorded here is a path the vending
                 # machine can package later without guessing.
                 "artifacts": [{"kind": a.kind, "path": a.path,
                                "description": a.description}
                               for a in result.artifacts]}))
    return result, stage_urn


async def record_judgment(objective_id: str, judgment: StageJudgment,
                          engine_name: str, bus: EventBus,
                          federation: FederationBridge) -> None:
    """Publish a gate decision as a fact, and as DataHub provenance.

    A verdict nobody can find later is not governance, it is a log line. Each
    judgment becomes a semantic event carrying every gate's evidence, and a
    dataset under the federation platform so the decision is queryable next to
    the work it judged.
    """
    # The gates reached these verdicts deterministically, with no clock in
    # reach. Stamping happens here, where a clock is legitimate.
    stamped = now_iso()
    for verdict in judgment.verdicts:
        if not verdict.checked_at:
            verdict.checked_at = stamped

    await bus.publish(SemanticEvent(
        kind="GatesEvaluated", engine=engine_name,
        subject=f"stage.{judgment.stage_seq}.{judgment.engine}",
        objective_id=objective_id,
        payload={"stage_seq": judgment.stage_seq,
                 "engine": judgment.engine,
                 "decision": judgment.action,
                 "summary": judgment.summary(),
                 "verdicts": [v.model_dump(mode="json")
                              for v in judgment.verdicts]}))
    await federation.emit_judgment(objective_id, judgment)


def skipped_result(stage: PlannedStage) -> ExecuteResult:
    """A stage that was deliberately not run.

    Modeled as a completed result carrying `skipped`, rather than a failure:
    an evolution run that finds no software to rebuild has not gone wrong, it
    has correctly done less work. The reason travels in provenance so the
    record shows *why* a stage was passed over.
    """
    return ExecuteResult(
        status="completed",
        outputs={"skipped": True, "reason": stage.skip_reason},
        # An explicit, DERIVED ref rather than the default factory: this runs
        # inside the workflow sandbox, where the default's uuid4 would be a
        # determinism violation. A skipped stage never executed anything, so
        # naming it after the stage is also more honest than a random id.
        provenance=Provenance(ref=ExecutionRef(
                                  execution_id=f"skipped.{stage.seq}."
                                               f"{stage.engine}"),
                              engine=stage.engine,
                              capability=stage.capability,
                              notes=[f"skipped: {stage.skip_reason}"]))


def was_skipped(result: ExecuteResult) -> bool:
    return bool(result.outputs.get("skipped"))


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
    skipped = 0
    # Deliberately ragged: a run that stopped early has fewer results
    # than stages, and zip stopping at the shorter one IS the intent.
    for stage, result in zip(pipeline.stages, stage_results, strict=False):
        if result.status != "completed":
            status = "failed"
            error = (f"stage {stage.seq} ({stage.capability}) failed: "
                     f"{result.error}")
            break
        if was_skipped(result):
            # A skipped stage contributes nothing to acc, so later stages
            # fall through to their own fallbacks instead of consuming a
            # placeholder as if it were real output.
            skipped += 1
            continue
        acc[stage.engine] = result.outputs
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
                 "stages_completed": len(stage_results) - skipped,
                 "stages_skipped": skipped,
                 "orchestrator": orchestrator,
                 # The cross-domain identity node, recorded durably. Without
                 # it the event log is not the authority on what this system
                 # published — objectives and stages arrive as event subjects,
                 # but the concept lived only in the returned result, which
                 # nothing persists. Anything rebuilding DataHub state from
                 # the log silently omitted it.
                 "concept_urn": concept_urn,
                 "datahub": federation.status}))

    artifacts: list[ArtifactRef] = []
    verdicts: list[Verdict] = []
    for r in stage_results:
        artifacts.extend(r.artifacts)
        # Every stage's own checks, carried up. A composed run that reported
        # only its composition gates would be claiming the whole objective was
        # verified while hiding what each engine actually proved — and the
        # engine-level checks are the ones with test results behind them.
        verdicts.extend(r.verdicts)
    by_seq = {s.seq: r
              for s, r in zip(pipeline.stages, stage_results, strict=False)}
    outputs = {
        "objective_id": objective_id,
        "topic": topic,
        "status": status,
        "stages": [{"seq": s.seq, "engine": s.engine,
                    "capability": s.capability,
                    "ran": not (s.seq in by_seq and was_skipped(by_seq[s.seq])),
                    "outputs": (by_seq[s.seq].outputs if s.seq in by_seq
                                and was_skipped(by_seq[s.seq])
                                else acc.get(s.engine, {}))}
                   for s in pipeline.stages],
        "stages_skipped": skipped,
        "concept_urn": concept_urn,
        "objective_urn": objective_urn,
    }
    return ExecuteResult(
        status=status, outputs=outputs, artifacts=artifacts,
        verdicts=verdicts, error=error,
        provenance=Provenance(
            engine=engine_name, capability=pipeline.name,
            ref=ExecutionRef(objective_id=objective_id,
                             workflow_id=workflow_id),
            started_at=started_at, finished_at=now_iso(),
            datahub_urns=[objective_urn] if objective_urn else [],
            notes=[f"orchestrator: {orchestrator}"],
            children=[r.provenance for r in stage_results]))
