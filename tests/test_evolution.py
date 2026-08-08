"""Evolution: the system reacts to new information about what it already built.

The claim under test is not "it can re-run things" — it is that the system
reads its OWN history to decide what actually needs redoing, and skips the
rest. A first run on a new subject must do the minimum; a later run on a
subject with existing artifacts must update exactly those.
"""

from __future__ import annotations

from one_engine.contract import ExecuteRequest, ExecutionRef
from one_engine.federation import impact


async def test_impact_on_an_unknown_subject_finds_nothing(bus):
    report = impact.analyze("Something Never Studied", bus)
    assert report.is_new_subject
    assert report.prior_objectives == []
    assert report.affected == {}
    assert set(report.unaffected) == {"research", "university", "software",
                                      "web"}


async def test_impact_reads_the_systems_own_history(unified, bus):
    """After a full build, the system knows what it made and where."""
    await unified.execute(ExecuteRequest(
        capability="compose.learning_platform",
        inputs={"topic": "WebGPU compute shaders"},
        ref=ExecutionRef(objective_id="obj-built")))

    report = impact.analyze("WebGPU compute shaders", bus)
    assert not report.is_new_subject
    assert report.prior_objectives == ["obj-built"]
    assert set(report.affected) == {"research", "university", "software",
                                    "web"}
    assert report.affected["software"]["project_id"] == "p1"
    assert report.affected["software"]["product_name"] == "FakeAcademy"
    assert report.affected["university"]["session_id"] == "c1"


async def test_impact_matches_on_concept_identity_not_raw_text(unified, bus):
    """'WebGPU Compute Shaders' and 'webgpu compute shaders' are the same
    subject — identity is the concept slug, the same rule the federation uses
    when it publishes a concept."""
    await unified.execute(ExecuteRequest(
        capability="compose.learning_platform",
        inputs={"topic": "WebGPU Compute Shaders"},
        ref=ExecutionRef(objective_id="obj-caps")))

    report = impact.analyze("webgpu   compute shaders", bus)
    assert report.prior_objectives == ["obj-caps"]
    assert report.concept_slug == "webgpu-compute-shaders"


async def test_evolving_a_new_subject_only_researches(unified, bus):
    """Nothing exists yet, so there is nothing to update: research runs,
    the three downstream stages skip themselves. Doing less is correct
    behavior here, not a failure."""
    result = await unified.execute(ExecuteRequest(
        capability="compose.evolve", inputs={"topic": "Brand New Thing"}))

    assert result.status == "completed"
    assert result.outputs["stages_skipped"] == 3
    ran = {s["engine"]: s["ran"] for s in result.outputs["stages"]}
    assert ran == {"research": True, "university": False,
                   "software": False, "web": False}
    # Only the stage that ran cost an engine call.
    assert [c.engine for c in result.provenance.children
            if "skipped" not in "".join(c.notes)] == ["fake-research"]


async def test_evolving_a_known_subject_updates_everything_affected(unified,
                                                                    bus):
    await unified.execute(ExecuteRequest(
        capability="compose.learning_platform",
        inputs={"topic": "WebGPU compute shaders"},
        ref=ExecutionRef(objective_id="obj-first")))

    result = await unified.execute(ExecuteRequest(
        capability="compose.evolve",
        inputs={"topic": "WebGPU compute shaders"},
        ref=ExecutionRef(objective_id="obj-evolve")))

    assert result.status == "completed"
    assert result.outputs["stages_skipped"] == 0
    assert all(s["ran"] for s in result.outputs["stages"])
    # The update was informed by what existed before: the previous product
    # name reached the rebuild request.
    stages = {s["engine"]: s["outputs"] for s in result.outputs["stages"]}
    assert "FakeAcademy" in stages["software"]["received_request"]
    assert "recently changed" in stages["software"]["received_request"]


async def test_impact_is_narrated_before_any_stage_runs(unified, bus):
    await unified.execute(ExecuteRequest(
        capability="compose.learning_platform",
        inputs={"topic": "Rust async"},
        ref=ExecutionRef(objective_id="obj-a")))
    await unified.execute(ExecuteRequest(
        capability="compose.evolve", inputs={"topic": "Rust async"},
        ref=ExecutionRef(objective_id="obj-b")))

    evolve = [e for e in bus.recent() if e.objective_id == "obj-b"]
    kinds = [e.kind for e in evolve]
    # Impact is determined FIRST — the decision precedes the work.
    assert kinds[0] == "ImpactAnalyzed"
    assert kinds[1] == "ObjectiveStarted"
    assert evolve[0].payload["is_new_subject"] is False
    assert set(evolve[0].payload["affected"]) == {"research", "university",
                                                  "software", "web"}


async def test_a_skipped_stage_records_why(unified):
    result = await unified.execute(ExecuteRequest(
        capability="compose.evolve", inputs={"topic": "Unknown Subject"}))
    skipped = [c for c in result.provenance.children
               if any(n.startswith("skipped:") for n in c.notes)]
    assert len(skipped) == 3
    assert any("no existing curriculum" in n
               for c in skipped for n in c.notes)
    assert any("no existing software" in n for c in skipped for n in c.notes)
