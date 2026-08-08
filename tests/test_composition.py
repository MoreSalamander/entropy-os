"""Composition: four engines behave as one, without becoming one."""

from __future__ import annotations

from one_engine.contract import ExecuteRequest, ExecutionRef
from one_engine.orchestration.runtime import EVENT_POLL_INTERVAL_S


async def test_composite_exposes_members_capabilities_as_its_own(unified):
    manifest = await unified.describe()
    names = {c.name for c in manifest.capabilities}
    assert {"research.investigate", "university.design_curriculum",
            "software.build", "web.generate_site",
            "compose.learning_platform"} <= names
    # Opacity: every capability is served BY the composite as far as callers
    # can see. Which member ran is provenance, not interface.
    assert {c.engine for c in manifest.capabilities} == {"one-engine"}
    assert manifest.identity.kind == "composite"


async def test_composition_tree_is_self_describing(unified):
    """'What systems compose you?' answered by the contract itself."""
    manifest = await unified.describe()
    tree = manifest.identity.composition
    assert tree.kind == "composite"
    assert {m.name for m in tree.members} == {
        "fake-research", "fake-university", "fake-software", "fake-web"}
    assert all(m.kind == "leaf" for m in tree.members)


async def test_atomic_passthrough_nests_provenance(unified):
    result = await unified.execute(ExecuteRequest(
        capability="research.investigate", inputs={"topic": "Taichi"}))
    assert result.status == "completed"
    assert result.provenance.engine == "one-engine"
    # One level down: the member that actually did the work.
    assert [c.engine for c in result.provenance.children] == ["fake-research"]


async def test_composed_pipeline_flows_outputs_across_domains(unified):
    """The load-bearing claim of cross-domain intelligence: what one engine
    learns must actually shape what the next one is asked to do."""
    result = await unified.execute(ExecuteRequest(
        capability="compose.learning_platform",
        inputs={"topic": "WebGPU compute shaders"}))
    assert result.status == "completed"

    stages = {s["engine"]: s["outputs"] for s in result.outputs["stages"]}
    # university's learning_order reached software's request…
    assert "basics, internals, practice" in stages["software"]["received_request"]
    # …and software's product name reached web's request.
    assert "FakeAcademy" in stages["web"]["received_request"]
    # Provenance nests one child per stage, in order.
    assert [c.engine for c in result.provenance.children] == [
        "fake-research", "fake-university", "fake-software", "fake-web"]


async def test_objective_narrated_as_semantic_events(unified, bus):
    await unified.execute(ExecuteRequest(
        capability="compose.learning_platform", inputs={"topic": "Rust"},
        ref=ExecutionRef(objective_id="obj-narrate")))
    kinds = [e.kind for e in bus.recent()]
    assert kinds[0] == "ObjectiveStarted"
    assert kinds[-1] == "ObjectiveCompleted"
    assert kinds.count("StageCompleted") == 4
    # Member facts are carried up into the unified narration.
    assert {"ResearchCompleted", "CurriculumCreated", "SoftwareBuilt",
            "SiteGenerated"} <= set(kinds)
    assert all(e.objective_id == "obj-narrate" for e in bus.recent())


async def test_pipeline_stops_at_the_first_failed_stage(unified):
    """A composed run must fail honestly rather than continue on bad state:
    downstream stages consume upstream outputs, so continuing past a failure
    would generate confident work on top of nothing."""
    unified.members.pop("software")
    result = await unified.execute(ExecuteRequest(
        capability="compose.learning_platform", inputs={"topic": "Zig"}))
    assert result.status == "failed"
    assert "missing member 'software'" in result.error
    # web must NOT have run after the failure.
    assert len(result.provenance.children) == 3


async def test_degrades_honestly_without_datahub(unified):
    """DataHub down is degraded, never fatal — and the system says so rather
    than reporting itself healthy while silently losing provenance."""
    result = await unified.execute(ExecuteRequest(
        capability="compose.learning_platform", inputs={"topic": "Elixir"}))
    assert result.status == "completed"
    assert result.outputs["objective_urn"].startswith("urn:li:dataset:")

    health = await unified.health()
    assert health.status == "degraded"
    assert all(v == "ok" for k, v in health.checks.items()
               if k.startswith("member:")), "members are fine; the layers are not"
    assert "not reachable" in health.checks["datahub_federation"]
    assert health.checks["orchestrator"].startswith("inline (degraded")


async def test_health_is_down_when_nothing_is_reachable(unified, bus,
                                                        offline_federation):
    """No member answering is absence, not degradation — the composite has
    nothing to compose."""
    from one_engine.composite import CompositeEngine
    from one_engine.remote import RemoteEngine
    empty = CompositeEngine(
        name="one-engine",
        members={"research": RemoteEngine("http://127.0.0.1:9")},
        bus=bus, federation=offline_federation)
    assert (await empty.health()).status == "down"


async def test_provenance_names_the_orchestrator(unified):
    result = await unified.execute(ExecuteRequest(
        capability="compose.learning_platform", inputs={"topic": "Nim"}))
    assert "orchestrator: inline" in result.provenance.notes


async def test_member_progress_is_narrated_while_a_stage_runs(unified, bus,
                                                              members):
    """A stage that takes minutes must be visible while it runs, not only
    when it returns — and each fact must appear exactly once."""
    import asyncio

    from one_engine.contract import ArtifactRef, CapabilitySpec, FieldSpec
    from one_engine.adapters.base import LeafAdapter
    from .conftest import in_process_remote

    class SlowResearch(LeafAdapter):
        name = "slow-research"
        datahub_platform = "slow-research"
        events_emitted = ["ResearchPhaseAdvanced", "ResearchCompleted"]

        def capabilities(self):
            return [CapabilitySpec(
                name="research.investigate", summary="slow",
                inputs={"topic": FieldSpec(type="string", required=True)})]

        async def _run(self, req, emit):
            emit("ResearchPhaseAdvanced", subject="planning")
            # Long enough for the streamer to poll mid-flight.
            await asyncio.sleep(EVENT_POLL_INTERVAL_S * 1.5)
            emit("ResearchCompleted", subject="done")
            return {"session_id": "s1", "topic": req.inputs["topic"]}, [], [], []

    unified.members["research"] = in_process_remote(SlowResearch(),
                                                    "http://slow.test")
    unified.members.pop("university"); unified.members.pop("software")
    unified.members.pop("web")

    await unified.execute(ExecuteRequest(
        capability="compose.learning_platform", inputs={"topic": "Slow"},
        ref=ExecutionRef(objective_id="obj-slow")))

    kinds = [e.kind for e in bus.recent()]
    # Exactly once each, despite being both streamed and returned.
    assert kinds.count("ResearchPhaseAdvanced") == 1
    assert kinds.count("ResearchCompleted") == 1
    # And streamed BEFORE the stage finished.
    assert kinds.index("ResearchPhaseAdvanced") < kinds.index("StageCompleted")
