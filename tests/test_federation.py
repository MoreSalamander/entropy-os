"""Federation: cross-domain identity and provenance without flattening."""

from __future__ import annotations

from one_engine.federation.datahub import FederationBridge
from one_engine.federation.semantics import PRIMITIVES, primitive_for, slugify
from one_engine.orchestration.stages import concept_representations


def test_engine_platforms_stay_separate_from_the_federation_platform():
    """Federation adds a platform; it does not absorb the others. Each
    engine's URNs keep pointing at that engine's own DataHub platform."""
    fed = FederationBridge(platform="one-engine")
    assert fed.dataset_urn("objective.o1") == \
        "urn:li:dataset:(urn:li:dataPlatform:one-engine,objective.o1,PROD)"
    # The bridge can address another platform's dataset for lineage without
    # claiming ownership of it.
    assert fed.dataset_urn("session.s1", platform="research-engine") == \
        "urn:li:dataset:(urn:li:dataPlatform:research-engine,session.s1,PROD)"


def test_semantic_primitives_map_events_across_domains():
    """Two engines that know nothing about each other emit events that the
    federation can recognize as the same KIND of thing."""
    assert primitive_for("ResearchCompleted") == "Evidence"
    assert primitive_for("MasteryEvidenceRecorded") == "Evidence"
    assert primitive_for("SoftwareBuilt") == "Artifact"
    assert primitive_for("LessonBuilt") == "Artifact"
    assert primitive_for("SomethingUnmapped") == "Event"
    assert set(PRIMITIVES) >= {"Evidence", "Concept", "Requirement",
                               "Artifact", "Workflow"}


def test_identity_resolution_only_claims_what_actually_happened():
    """Cross-domain identity must carry receipts: a domain appears in the
    concept record only if it produced a real identifier."""
    acc = {"research": {"session_id": "sess-1"},
           "university": {"session_id": "study-1",
                          "learning_order": ["a", "b"]}}
    reps = concept_representations("WebGPU", acc)
    assert reps["research_session"] == "sess-1"
    assert reps["curriculum_session"] == "study-1"
    assert "software_project" not in reps, "no software ran; claim nothing"
    assert "web_project" not in reps


def test_slugs_are_stable_across_domains():
    assert slugify("WebGPU compute shaders") == "webgpu-compute-shaders"
    assert slugify("WebGPU  Compute  Shaders!") == "webgpu-compute-shaders"
    assert slugify("") == "unnamed"


async def test_emission_degrades_to_urns_when_gms_is_down():
    """Offline, the bridge still returns the URNs a run WOULD have — so
    provenance stays consistent and nothing raises."""
    fed = FederationBridge("http://127.0.0.1:9", "one-engine")
    assert await fed.probe() is False
    urn = await fed.emit_objective("obj-1", "t", [], "", [], "completed",
                                   "wf", "", "")
    assert urn.endswith("objective.obj-1,PROD)")
    assert "not reachable" in fed.status


async def test_the_event_log_names_every_dataset_the_run_published(
        unified, bus):
    """The event log is the authority on what this system published, and
    anything that rebuilds DataHub state reads it. All three federation
    dataset kinds must therefore appear in it.

    Regression-guards a real gap: objective and stage URNs arrive as event
    subjects, but the concept URN lived only in the returned result — which
    nothing persists — so a re-index driven by the log silently omitted the
    cross-domain identity node.
    """
    from one_engine.contract import ExecuteRequest

    result = await unified.execute(ExecuteRequest(
        capability="compose.learning_platform",
        inputs={"topic": "WebGPU compute shaders"}))

    published = {result.outputs["concept_urn"],
                 result.outputs["objective_urn"]}
    assert all(published), "the run must publish both a concept and an objective"

    logged: set[str] = set()
    for event in bus.recent():
        for value in [event.subject, *event.payload.values()]:
            if isinstance(value, str) and value.startswith("urn:li:dataset:"):
                logged.add(value)

    assert published <= logged, (
        f"published but never logged: {sorted(published - logged)}")
    # And the stages too, so a rebuild covers the whole graph.
    assert sum(1 for u in logged if ",stage." in u) == 4
