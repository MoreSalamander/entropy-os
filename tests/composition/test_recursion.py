"""Recursive composition — the central claim, tested rather than asserted.

A second-level system consumes the unified system through the same contract,
with the same client class, and cannot distinguish it from a leaf. Then the
move is available a third time, which is what "the four-engine composition is
not the final level" has to mean if it means anything.
"""

from __future__ import annotations

from entropy_os.composition.composite import CompositeEngine
from entropy_os.composition.contract import ExecuteRequest, FieldSpec
from entropy_os.composition.events.bus import EventBus
from entropy_os.composition.federation.datahub import FederationBridge
from entropy_os.composition.orchestration.stages import Acc, ComposedPipeline, PlannedStage

from .conftest import in_process_remote


def _delegate_whole_composition(inputs: dict, acc: Acc) -> dict:
    return {"topic": inputs["topic"]}


def _launch_page(inputs: dict, acc: Acc) -> dict:
    stages = acc.get("unified", {}).get("stages") or []
    product = next((s["outputs"].get("product_name") for s in stages
                    if s["outputs"].get("product_name")), "Unnamed")
    return {"request": f"Venture launch page for {product}"}


LAUNCH = ComposedPipeline(
    name="studio.launch_venture",
    summary="Commission a whole learning platform, then launch it.",
    inputs={"topic": FieldSpec(type="string", required=True)},
    stages=[PlannedStage(1, "unified", "compose.learning_platform",
                         _delegate_whole_composition),
            PlannedStage(2, "unified", "web.generate_site", _launch_page)])


def build_studio(unified, tmp_path) -> CompositeEngine:
    """System B: ONE member, addressed exactly the way the unified system
    addresses its own members."""
    return CompositeEngine(
        name="meta-studio",
        members={"unified": in_process_remote(unified,
                                              "http://unified.test")},
        bus=EventBus(tmp_path / "studio_events.jsonl"),
        federation=FederationBridge("http://127.0.0.1:9", "meta-studio"),
        datahub_platform="meta-studio",
        pipelines={LAUNCH.name: LAUNCH},
        description="A studio composed of one intelligence system.")


async def test_second_level_sees_a_plain_engine(unified, tmp_path):
    """From System B's side, the unified system is just an engine that
    happens to offer a lot of capabilities."""
    studio = build_studio(unified, tmp_path)
    manifest = await studio.describe()
    names = {c.name for c in manifest.capabilities}
    # It inherited its member's whole surface, including the member's OWN
    # composed capability — consumed as an ordinary capability.
    assert {"research.investigate", "software.build",
            "compose.learning_platform", "studio.launch_venture"} <= names
    assert {c.engine for c in manifest.capabilities} == {"meta-studio"}


async def test_composition_tree_nests_to_arbitrary_depth(unified, tmp_path):
    studio = build_studio(unified, tmp_path)
    tree = (await studio.describe()).identity.composition
    assert tree.name == "meta-studio" and tree.kind == "composite"
    assert len(tree.members) == 1

    inner = tree.members[0]
    assert inner.name == "one-engine" and inner.kind == "composite"
    assert {m.name for m in inner.members} == {
        "fake-research", "fake-university", "fake-software", "fake-web"}
    # Self-description descends the whole stack from a single call: this is
    # what makes "what systems compose you?" answerable at any level.


async def test_members_composed_capability_is_delegated_not_re_run(unified,
                                                                   tmp_path):
    """The correctness knife-edge of recursion: System B must treat its
    member's composed capability as ONE opaque capability call, not as a
    pipeline it can run itself. Its members are named 'unified' — it has no
    'research' or 'software' member, so re-running the member's pipeline
    locally would fail outright."""
    studio = build_studio(unified, tmp_path)
    assert "compose.learning_platform" not in studio.pipelines

    result = await studio.execute(ExecuteRequest(
        capability="compose.learning_platform", inputs={"topic": "CRDTs"}))
    assert result.status == "completed"
    # Delegated whole: one child, the member — the four engines beneath are
    # visible only if you descend further, which is optional by design.
    assert [c.engine for c in result.provenance.children] == ["one-engine"]
    grandchildren = [g.engine for g in result.provenance.children[0].children]
    assert grandchildren == ["fake-research", "fake-university",
                             "fake-software", "fake-web"]


async def test_second_level_pipeline_builds_on_a_whole_composition(unified,
                                                                   tmp_path):
    studio = build_studio(unified, tmp_path)
    result = await studio.execute(ExecuteRequest(
        capability="studio.launch_venture", inputs={"topic": "WebGPU"}))
    assert result.status == "completed"

    stages = result.outputs["stages"]
    assert stages[0]["capability"] == "compose.learning_platform"
    # Stage 2 consumed the OUTPUT of an entire four-engine composition.
    assert "FakeAcademy" in stages[1]["outputs"]["received_request"]
    # Artifacts from every level surface at the top: four engines' worth,
    # plus System B's own stage.
    assert [a.kind for a in result.artifacts] == [
        "report", "project", "site", "site"]


async def test_the_move_is_available_again_at_the_third_level(unified,
                                                             tmp_path):
    """If composition were special-cased for the four-engine case, this is
    where it would break. Same class, same client, one level higher."""
    studio = build_studio(unified, tmp_path)
    holding = CompositeEngine(
        name="holding-co",
        members={"studio": in_process_remote(studio, "http://studio.test")},
        bus=EventBus(tmp_path / "holding_events.jsonl"),
        federation=FederationBridge("http://127.0.0.1:9", "holding-co"),
        datahub_platform="holding-co", pipelines={})

    tree = (await holding.describe()).identity.composition
    assert tree.members[0].name == "meta-studio"
    assert tree.members[0].members[0].name == "one-engine"
    assert len(tree.members[0].members[0].members) == 4

    result = await holding.execute(ExecuteRequest(
        capability="studio.launch_venture", inputs={"topic": "Zig"}))
    assert result.status == "completed"
    # Three levels of nesting, resolved through one uniform mechanism.
    depth1 = result.provenance.children[0]           # meta-studio
    depth2 = depth1.children[0]                      # one-engine
    depth3 = depth2.children[0]                      # a leaf engine
    assert (depth1.engine, depth2.engine, depth3.engine) == (
        "meta-studio", "one-engine", "fake-research")
