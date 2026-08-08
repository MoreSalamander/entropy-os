"""Temporal workflows — durable execution for composed objectives.

The workflow owns what the system is DOING over time: stage sequencing,
retries, timeouts, human approval signals, cancellation, and the durable
history that lets a multi-hour objective survive a worker restart. It owns
none of what the system KNOWS — knowledge and semantic relationships live in
DataHub, written by the activities through the federation bridge.

Determinism rule observed here: this module imports only pure pipeline SHAPE
(stages.py has no I/O), and every effect happens inside an activity.
"""

from __future__ import annotations

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from ..contract import ExecuteResult
    from .runtime import skipped_result
    from .stages import COMPOSED_PIPELINES, StageOutcome

# Activity names are addressed as strings so the workflow never imports the
# activity module (which pulls in httpx, the bus, and the federation bridge).
START_ACTIVITY = "start_objective"
STAGE_ACTIVITY = "run_stage"
JUDGMENT_ACTIVITY = "record_judgment"
FINALIZE_ACTIVITY = "finalize_objective"

# Engines run local models and real builds; a stage may legitimately take
# tens of minutes. Retries are few and spaced: a failing local model rarely
# recovers in milliseconds, and hammering it makes things worse.
STAGE_RETRY = RetryPolicy(initial_interval=timedelta(seconds=10),
                          backoff_coefficient=2.0,
                          maximum_interval=timedelta(minutes=2),
                          maximum_attempts=2)
BOOKKEEPING_RETRY = RetryPolicy(initial_interval=timedelta(seconds=2),
                                maximum_attempts=3)


@workflow.defn(name="ComposedObjective")
class ComposedObjectiveWorkflow:
    """One composed objective, end to end.

    Signals:
        approve(note)  — release a stage waiting on human approval
        reject(note)   — abandon the objective at the approval gate
    Queries:
        progress()     — current stage, statuses, and approval state
    """

    def __init__(self) -> None:
        self._stage_status: list[dict] = []
        self._current: int = 0
        self._approved: bool | None = None
        self._approval_note: str = ""
        self._awaiting_approval: bool = False
        self._judgments: list[dict] = []
        self._held_by: str = ""      # which gate is holding, if any

    @workflow.signal
    def approve(self, note: str = "") -> None:
        self._approved, self._approval_note = True, note

    @workflow.signal
    def reject(self, note: str = "") -> None:
        self._approved, self._approval_note = False, note

    @workflow.query
    def progress(self) -> dict:
        return {"current_stage": self._current,
                "stages": self._stage_status,
                "awaiting_approval": self._awaiting_approval,
                "approval_note": self._approval_note,
                "held_by": self._held_by,
                "judgments": self._judgments}

    @workflow.run
    async def run(self, capability: str, inputs: dict,
                  objective_id: str) -> ExecuteResult:
        # The worker serves the unified system, whose pipelines are the
        # module-level registry. Stage SHAPE is read here; stage EFFECTS
        # happen only in activities.
        pipeline = COMPOSED_PIPELINES[capability]
        info = workflow.info()
        workflow_id = info.workflow_id
        # Deterministic clock: replay must reproduce the same start stamp.
        started_at = info.start_time.isoformat()

        # The start activity also gathers whatever the pipeline needs before
        # any stage runs — for an evolving pipeline, the impact report that
        # decides which stages are worth running at all.
        acc: dict[str, dict] = await workflow.execute_activity(
            START_ACTIVITY,
            args=[capability, inputs, objective_id, "temporal"],
            start_to_close_timeout=timedelta(minutes=2),
            retry_policy=BOOKKEEPING_RETRY)

        # Optional human gate before a chosen stage. Off by default: a gate
        # nobody asked for is friction, but the capability to pause a long
        # autonomous run for a human decision has to exist.
        approve_before = int(inputs.get("approve_before_stage", 0) or 0)

        results: list[ExecuteResult] = []
        stage_urns: list[str] = []
        prev_urn = ""

        for stage in pipeline.stages:
            self._current = stage.seq

            # Deterministic, data-only predicate over state the workflow
            # already holds — safe to evaluate here, and it means a skipped
            # stage costs no activity, no engine call, and no time.
            if stage.should_skip(inputs, acc):
                results.append(skipped_result(stage))
                self._stage_status.append({"seq": stage.seq,
                                           "engine": stage.engine,
                                           "capability": stage.capability,
                                           "status": "skipped",
                                           "reason": stage.skip_reason})
                continue

            if approve_before and stage.seq == approve_before:
                self._awaiting_approval = True
                await workflow.wait_condition(
                    lambda: self._approved is not None)
                self._awaiting_approval = False
                if self._approved is False:
                    break

            outcome = await workflow.execute_activity(
                STAGE_ACTIVITY,
                args=[capability, stage.seq, objective_id, workflow_id,
                      inputs, acc, prev_urn],
                # Activities addressed by NAME carry no inferable return
                # type, so result_type is what turns the JSON payload back
                # into a typed model instead of a bare dict.
                result_type=StageOutcome,
                # The activity's own window must outlive the engine's work;
                # heartbeat-free because engines are opaque behind HTTP.
                start_to_close_timeout=timedelta(
                    seconds=stage.timeout_s + 300),
                retry_policy=STAGE_RETRY)

            results.append(outcome.result)
            if outcome.stage_urn:
                stage_urns.append(outcome.stage_urn)
                prev_urn = outcome.stage_urn

            # ---- the deterministic scaffold decides ------------------------
            # The engine proposed a result; gates now say whether the run may
            # continue past it. Pure functions of what the contract recorded,
            # evaluated HERE rather than in an activity, so the decision is
            # the orchestrator's and lands in durable workflow history.
            judgment = stage.judge(outcome.result)
            self._judgments.append(judgment.model_dump(mode="json"))
            self._stage_status.append({"seq": stage.seq,
                                       "engine": stage.engine,
                                       "capability": stage.capability,
                                       "status": outcome.result.status,
                                       "gates": judgment.summary(),
                                       "decision": judgment.action})
            await workflow.execute_activity(
                JUDGMENT_ACTIVITY,
                args=[objective_id, judgment],
                start_to_close_timeout=timedelta(minutes=2),
                retry_policy=BOOKKEEPING_RETRY)

            if judgment.action == "block":
                # A hard fact says no. Stop rather than build on it.
                self._held_by = ", ".join(v.gate for v in judgment.failed)
                break
            if judgment.action == "hold":
                # A judgment call: the gate settled the fact, a person decides
                # the consequence. The run waits rather than assuming.
                self._held_by = ", ".join(v.gate for v in judgment.failed)
                self._approved = None
                self._awaiting_approval = True
                await workflow.wait_condition(
                    lambda: self._approved is not None)
                self._awaiting_approval = False
                if self._approved is False:
                    break
                self._held_by = ""

            if outcome.result.status != "completed":
                break
            acc[stage.engine] = outcome.result.outputs

        return await workflow.execute_activity(
            FINALIZE_ACTIVITY,
            args=[capability, inputs, objective_id, workflow_id, "temporal",
                  results, stage_urns, started_at],
            result_type=ExecuteResult,
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=BOOKKEEPING_RETRY)
