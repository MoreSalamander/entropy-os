"""Durable orchestration, against a REAL Temporal cluster.

These tests skip when Temporal is not running, because their whole value is
that nothing here is mocked: a real worker, real activities, real workflow
history, real signals. What they deliberately do NOT exercise is the four
production engines — the members are fakes, so a failure here is
unambiguously an orchestration failure rather than a model or build failure.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from temporalio.client import Client
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.worker import Worker

from one_engine.contract import ExecuteResult, FieldSpec
from one_engine.events.bus import EventBus
from one_engine.federation.datahub import FederationBridge
from one_engine.orchestration.launcher import TemporalLauncher
from one_engine.orchestration.stages import (Acc, ComposedPipeline,
                                             PlannedStage)
from one_engine.orchestration.worker import ObjectiveActivities
from one_engine.orchestration.workflows import ComposedObjectiveWorkflow

from .conftest import (FakeResearch, FakeSoftware, FakeUniversity, FakeWeb,
                       in_process_remote)

ADDRESS = "localhost:7233"


def _fast_pipeline() -> ComposedPipeline:
    """The real four-stage shape, with short timeouts so a failure surfaces
    as a test failure rather than a hang."""
    def research(inputs: dict, acc: Acc) -> dict:
        return {"topic": inputs["topic"]}

    def curriculum(inputs: dict, acc: Acc) -> dict:
        return {"goal": f"learn {inputs['topic']}"}

    def build(inputs: dict, acc: Acc) -> dict:
        order = ", ".join(acc["university"]["learning_order"])
        return {"request": f"platform teaching {order}"}

    def site(inputs: dict, acc: Acc) -> dict:
        return {"request": f"site for {acc['software']['product_name']}"}

    return ComposedPipeline(
        name="compose.learning_platform",
        summary="test pipeline",
        inputs={"topic": FieldSpec(type="string", required=True)},
        stages=[
            PlannedStage(1, "research", "research.investigate", research, 30),
            PlannedStage(2, "university", "university.design_curriculum",
                         curriculum, 30),
            PlannedStage(3, "software", "software.build", build, 30),
            PlannedStage(4, "web", "web.generate_site", site, 30),
        ])


async def _client() -> Client:
    return await Client.connect(ADDRESS,
                                data_converter=pydantic_data_converter)


@pytest.fixture
async def temporal_client():
    try:
        return await asyncio.wait_for(_client(), timeout=5)
    except Exception:
        pytest.skip(f"Temporal not running at {ADDRESS}")


@pytest.fixture
def durable_members():
    return {"research": in_process_remote(FakeResearch(), "http://r.test"),
            "university": in_process_remote(FakeUniversity(), "http://u.test"),
            "software": in_process_remote(FakeSoftware(), "http://s.test"),
            "web": in_process_remote(FakeWeb(), "http://w.test")}


async def test_workflow_runs_the_composed_pipeline_durably(
        temporal_client, durable_members, tmp_path):
    """The full durable path: workflow → activities → contract → members,
    with the same runtime the inline path uses."""
    pipeline = _fast_pipeline()
    bus = EventBus(tmp_path / "events.jsonl")
    federation = FederationBridge("http://127.0.0.1:9", "one-engine")
    queue = f"one-engine-test-{uuid.uuid4().hex[:8]}"
    acts = ObjectiveActivities(durable_members, bus, federation,
                               engine_name="one-engine",
                               pipelines={pipeline.name: pipeline})

    async with Worker(temporal_client, task_queue=queue,
                      workflows=[ComposedObjectiveWorkflow],
                      activities=[acts.start_objective, acts.run_stage,
                                  acts.finalize_objective]):
        launcher = TemporalLauncher(temporal_client, queue)
        objective_id = f"obj-test-{uuid.uuid4().hex[:8]}"
        result = await launcher("compose.learning_platform",
                                {"topic": "WebGPU"}, objective_id)

    assert result.status == "completed"
    assert result.outputs["objective_id"] == objective_id
    # Cross-domain flow survived the process boundaries between activities.
    stages = {s["engine"]: s["outputs"] for s in result.outputs["stages"]}
    assert "basics, internals, practice" in stages["software"]["received_request"]
    assert "FakeAcademy" in stages["web"]["received_request"]
    # Provenance records the durable path and the workflow that owned it.
    assert "orchestrator: temporal" in result.provenance.notes
    assert result.provenance.ref.workflow_id == objective_id
    assert [c.engine for c in result.provenance.children] == [
        "fake-research", "fake-university", "fake-software", "fake-web"]

    kinds = [e.kind for e in bus.recent()]
    assert kinds[0] == "ObjectiveStarted"
    assert kinds[-1] == "ObjectiveCompleted"
    assert kinds.count("StageCompleted") == 4


async def test_human_approval_gate_blocks_then_releases(
        temporal_client, durable_members, tmp_path):
    """Human intervention as a first-class orchestration feature: the run
    genuinely waits, is queryable while waiting, and proceeds on a signal."""
    pipeline = _fast_pipeline()
    bus = EventBus(tmp_path / "events.jsonl")
    federation = FederationBridge("http://127.0.0.1:9", "one-engine")
    queue = f"one-engine-gate-{uuid.uuid4().hex[:8]}"
    acts = ObjectiveActivities(durable_members, bus, federation,
                               engine_name="one-engine",
                               pipelines={pipeline.name: pipeline})

    async with Worker(temporal_client, task_queue=queue,
                      workflows=[ComposedObjectiveWorkflow],
                      activities=[acts.start_objective, acts.run_stage,
                                  acts.finalize_objective]):
        objective_id = f"obj-gate-{uuid.uuid4().hex[:8]}"
        handle = await temporal_client.start_workflow(
            "ComposedObjective",
            args=["compose.learning_platform",
                  {"topic": "Rust", "approve_before_stage": 3},
                  objective_id],
            id=objective_id, task_queue=queue,
            result_type=ExecuteResult)

        # Wait for the gate rather than sleeping a fixed amount.
        for _ in range(100):
            progress = await handle.query("progress")
            if progress["awaiting_approval"]:
                break
            await asyncio.sleep(0.1)
        assert progress["awaiting_approval"] is True
        assert progress["current_stage"] == 3
        assert len(progress["stages"]) == 2, "must pause BEFORE stage 3"

        await handle.signal("approve", "ship it")
        result = await handle.result()

    assert result.status == "completed"
    assert len(result.provenance.children) == 4


async def test_rejection_at_the_gate_stops_the_run_honestly(
        temporal_client, durable_members, tmp_path):
    pipeline = _fast_pipeline()
    bus = EventBus(tmp_path / "events.jsonl")
    federation = FederationBridge("http://127.0.0.1:9", "one-engine")
    queue = f"one-engine-reject-{uuid.uuid4().hex[:8]}"
    acts = ObjectiveActivities(durable_members, bus, federation,
                               engine_name="one-engine",
                               pipelines={pipeline.name: pipeline})

    async with Worker(temporal_client, task_queue=queue,
                      workflows=[ComposedObjectiveWorkflow],
                      activities=[acts.start_objective, acts.run_stage,
                                  acts.finalize_objective]):
        objective_id = f"obj-rej-{uuid.uuid4().hex[:8]}"
        handle = await temporal_client.start_workflow(
            "ComposedObjective",
            args=["compose.learning_platform",
                  {"topic": "Nim", "approve_before_stage": 2},
                  objective_id],
            id=objective_id, task_queue=queue,
            result_type=ExecuteResult)
        for _ in range(100):
            progress = await handle.query("progress")
            if progress["awaiting_approval"]:
                break
            await asyncio.sleep(0.1)
        await handle.signal("reject", "not now")
        result = await handle.result()

    assert result.status == "failed"
    assert "stopped after 1 of 4 stages" in result.error
    # The partial run is still fully recorded — a rejected objective is
    # history, not a hole.
    assert len(result.provenance.children) == 1
    assert [e.kind for e in bus.recent()][-1] == "ObjectiveCompleted"
