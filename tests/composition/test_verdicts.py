"""Verdicts survive the contract, and say honest things.

An engine that checks its own work and cannot REPORT the check has, from a
consumer's point of view, not checked anything. These tests hold the seam
that carries those checks: that a verdict reaches a caller across HTTP with
its determinism intact, that an empty list is never read as success, and that
the two ways of being un-verified — failed and not-run — stay distinguishable.
"""

from __future__ import annotations

import pytest

from entropy_os.composition.adapters.base import LeafAdapter
from entropy_os.composition.contract import (
    CapabilitySpec,
    Determinism,
    ExecuteRequest,
    FieldSpec,
    Verdict,
)
from entropy_os.composition.scaffold import GateVerdict

from .conftest import in_process_remote


class Checker(LeafAdapter):
    """An engine that runs three checks: a fact, an opinion, and one that
    could not run at all. All three are things real engines produce."""

    name = "checker"
    datahub_platform = "checker"

    def capabilities(self):
        return [CapabilitySpec(
            name="check.run", summary="run some checks",
            inputs={"subject": FieldSpec(type="string", required=True)},
            outputs={"ok": FieldSpec(type="boolean")})]

    async def _run(self, req, emit, vouch):
        vouch(gate="tests", determinism=Determinism.HARD, passed=True,
              evidence="12 passed in 0.4s", count=12)
        vouch(gate="reviewer", determinism=Determinism.SOFT, passed=False,
              evidence="the judge model disliked the naming")
        vouch(gate="build", determinism=Determinism.HARD, passed=False,
              evidence="build gate did not run (npm unavailable)", ran=False)
        return {"ok": True}, [], [], []


class Silent(LeafAdapter):
    """An engine that checks nothing and says so by saying nothing."""

    name = "silent"
    datahub_platform = "silent"

    def capabilities(self):
        return [CapabilitySpec(name="check.run", summary="no checks",
                               inputs={}, outputs={})]

    async def _run(self, req, emit, vouch):
        return {"ok": True}, [], [], []


async def test_verdicts_cross_the_wire_with_their_determinism_intact():
    """The point of the seam: a consumer on the other side of HTTP can tell a
    test result from a model's opinion. If determinism did not survive
    serialization, every consumer would have to guess — and the flattering
    guess is the one that gets made."""
    remote = in_process_remote(Checker(), "http://checker.test")
    result = await remote.execute(ExecuteRequest(
        capability="check.run", inputs={"subject": "x"}))

    assert result.status == "completed"
    by_gate = {v.gate: v for v in result.verdicts}
    assert set(by_gate) == {"tests", "reviewer", "build"}
    assert by_gate["tests"].determinism is Determinism.HARD
    assert by_gate["reviewer"].determinism is Determinism.SOFT
    # Evidence is the whole point of a verdict; a bare boolean is what this
    # replaced.
    assert by_gate["tests"].evidence == "12 passed in 0.4s"
    assert by_gate["tests"].facts["count"] == 12


async def test_a_failed_check_and_a_skipped_one_are_both_not_passed():
    """Two different reasons to be unverified, neither of which is success.
    A surface that folded 'did not run' into 'passed' would be lying in the
    most consequential direction."""
    remote = in_process_remote(Checker(), "http://checker.test")
    result = await remote.execute(ExecuteRequest(
        capability="check.run", inputs={"subject": "x"}))

    by_gate = {v.gate: v for v in result.verdicts}
    assert by_gate["reviewer"].passed is False
    assert by_gate["build"].passed is False
    assert by_gate["build"].facts["ran"] is False
    # …and the distinction is still legible, not collapsed into one flag.
    assert "did not run" in by_gate["build"].evidence


async def test_no_verdicts_means_nothing_was_reported_not_that_all_is_well():
    """An engine that reports no verdicts is making no claim. The test exists
    to pin the semantics: `verdicts == []` is silence, and a consumer must not
    be able to point at this and call it verification."""
    remote = in_process_remote(Silent(), "http://silent.test")
    result = await remote.execute(ExecuteRequest(capability="check.run",
                                                 inputs={}))
    assert result.status == "completed"
    assert result.verdicts == []
    assert not any(v.passed for v in result.verdicts)


async def test_a_failing_execution_still_reports_what_it_checked():
    """The verdicts collected before the failure are still true, and are the
    most useful thing a caller has when something breaks."""

    class Breaks(Checker):
        name = "breaks"

        async def _run(self, req, emit, vouch):
            vouch(gate="tests", determinism=Determinism.HARD, passed=False,
                  evidence="1 failed, 11 passed")
            raise RuntimeError("generation crashed after verification")

    remote = in_process_remote(Breaks(), "http://breaks.test")
    result = await remote.execute(ExecuteRequest(
        capability="check.run", inputs={"subject": "x"}))

    assert result.status == "failed"
    assert [v.gate for v in result.verdicts] == ["tests"]
    assert result.verdicts[0].passed is False


def test_composition_gate_verdicts_are_the_same_vocabulary():
    """One definition of 'hard', whether the check ran inside an engine or
    between two of them. Two definitions would eventually drift, and a drifted
    trust vocabulary is worse than none."""
    g = GateVerdict(gate="verification_passed", determinism=Determinism.HARD,
                    passed=False, evidence="stage reported failure",
                    stage_seq=3, engine="software")
    assert isinstance(g, Verdict)
    # The extra fields are about WHERE the check happened, not what it means.
    assert g.model_dump().keys() >= {"gate", "determinism", "passed",
                                     "evidence", "facts", "stage_seq",
                                     "engine"}


@pytest.mark.parametrize("value", ["hard", "soft", "human"])
def test_the_three_determinisms_are_the_whole_vocabulary(value):
    """A closed vocabulary is what makes the label meaningful; an engine
    cannot invent a fourth, more flattering category."""
    assert Determinism(value).value == value
    with pytest.raises(ValueError):
        Determinism("probably")


# --------------------------------------------------------------------------- #
# Serving artifacts: the engine that made it, and nothing outside its root
# --------------------------------------------------------------------------- #

class Producer(Checker):
    """An engine with a real storage root, so file serving has a boundary."""

    name = "producer"
    datahub_platform = "producer"

    def __init__(self, root):
        super().__init__()
        self._root = root

    def artifact_root(self):
        return self._root


async def test_an_engine_serves_a_file_from_its_own_artifact_root(tmp_path):
    root = tmp_path / "engine"
    (root / "project").mkdir(parents=True)
    (root / "project" / "main.py").write_text("print('hello')\n")

    remote = in_process_remote(Producer(root), "http://producer.test")
    r = await remote._client.get("/artifacts/file",
                                 params={"path": str(root / "project"),
                                         "rel": "main.py"})
    assert r.status_code == 200
    assert r.json()["text"] == "print('hello')\n"


async def test_a_path_outside_the_root_is_refused(tmp_path):
    """`path` comes from the caller. Without the containment check this route
    is an arbitrary-file read on the host, so the refusal is the feature."""
    root = tmp_path / "engine"
    root.mkdir(parents=True)
    secret = tmp_path / "secret.txt"
    secret.write_text("not yours")

    remote = in_process_remote(Producer(root), "http://producer.test")

    r = await remote._client.get("/artifacts/file", params={"path": str(secret)})
    assert r.status_code == 404

    # …and the same thing dressed up as a relative escape.
    r = await remote._client.get("/artifacts/file",
                                 params={"path": str(root), "rel": "../secret.txt"})
    assert r.status_code == 404


async def test_a_symlink_pointing_out_of_the_root_is_refused(tmp_path):
    """Resolution happens BEFORE the containment test, so a link cannot walk
    out of the root while still looking like it is inside it."""
    root = tmp_path / "engine"
    root.mkdir(parents=True)
    secret = tmp_path / "secret.txt"
    secret.write_text("not yours")
    (root / "escape.txt").symlink_to(secret)

    remote = in_process_remote(Producer(root), "http://producer.test")
    r = await remote._client.get("/artifacts/file",
                                 params={"path": str(root), "rel": "escape.txt"})
    assert r.status_code == 404


async def test_an_engine_without_storage_says_so_rather_than_guessing(tmp_path):
    """No root means the engine does not serve files. It must not fall back to
    reading the filesystem on the caller's word."""
    remote = in_process_remote(Checker(), "http://checker.test")
    r = await remote._client.get("/artifacts/file", params={"path": str(tmp_path)})
    assert r.status_code == 404


async def test_a_composite_serves_a_members_artifact_without_owning_a_disk(tmp_path):
    """The composite has no storage root, so it cannot check containment and
    must not try. It asks the members, and the one that owns the file
    answers."""
    from entropy_os.composition.composite import CompositeEngine
    from entropy_os.composition.events.bus import EventBus
    from entropy_os.composition.federation.datahub import FederationBridge

    root = tmp_path / "web"
    (root / "site").mkdir(parents=True)
    (root / "site" / "page.tsx").write_text("export default Page\n")

    unified = CompositeEngine(
        name="unified",
        members={"web": in_process_remote(Producer(root), "http://web.test"),
                 "silent": in_process_remote(Silent(), "http://silent.test")},
        bus=EventBus(tmp_path / "events.jsonl"),
        federation=FederationBridge(gms_url="http://127.0.0.1:9", platform="t"))

    got = await unified.artifact_file(str(root / "site"), "page.tsx")
    assert got["text"] == "export default Page\n"
    # Provenance of the read: which engine actually answered.
    assert got["engine"] == "producer"


async def test_a_composite_cannot_reach_outside_every_members_root(tmp_path):
    """Asking all members is only safe because each refuses for its own root.
    If the composite ever started resolving paths itself, this is the test
    that would stop being true."""
    from entropy_os.composition.composite import CompositeEngine
    from entropy_os.composition.contract import ArtifactNotServed
    from entropy_os.composition.events.bus import EventBus
    from entropy_os.composition.federation.datahub import FederationBridge

    root = tmp_path / "web"
    root.mkdir(parents=True)
    secret = tmp_path / "secret.txt"
    secret.write_text("not yours")

    unified = CompositeEngine(
        name="unified",
        members={"web": in_process_remote(Producer(root), "http://web.test")},
        bus=EventBus(tmp_path / "events.jsonl"),
        federation=FederationBridge(gms_url="http://127.0.0.1:9", platform="t"))

    with pytest.raises(ArtifactNotServed):
        await unified.artifact_file(str(secret))
    with pytest.raises(ArtifactNotServed):
        await unified.artifact_file(str(root), "../secret.txt")


async def test_verdicts_survive_composition(tmp_path):
    """The gap that shipped: every earlier test here exercised a LEAF, so
    nothing noticed that the composite rebuilt the result and left the
    verdicts behind. A real run through the composite is where it showed up —
    an engine's checks stopped existing the moment it was composed."""
    from entropy_os.composition.composite import CompositeEngine
    from entropy_os.composition.events.bus import EventBus
    from entropy_os.composition.federation.datahub import FederationBridge

    unified = CompositeEngine(
        name="unified",
        members={"checker": in_process_remote(Checker(), "http://checker.test")},
        bus=EventBus(tmp_path / "events.jsonl"),
        federation=FederationBridge(gms_url="http://127.0.0.1:9", platform="t"))

    result = await unified.execute(ExecuteRequest(
        capability="check.run", inputs={"subject": "x"}))

    by_gate = {v.gate: v for v in result.verdicts}
    assert set(by_gate) == {"tests", "reviewer", "build"}, (
        "the composite must carry its member's verdicts, not just its own")
    assert by_gate["tests"].determinism is Determinism.HARD
    assert by_gate["reviewer"].determinism is Determinism.SOFT


async def test_the_acceptance_rule_reads_a_composed_result(tmp_path):
    """End to end in the shape the wedge actually uses it: run through the
    composite, then decide. Empty verdicts here would have quietly refused
    every vend."""
    from entropy_os.composition.composite import CompositeEngine
    from entropy_os.composition.events.bus import EventBus
    from entropy_os.composition.federation.datahub import FederationBridge
    from entropy_os.vending import decide

    unified = CompositeEngine(
        name="unified",
        members={"checker": in_process_remote(Checker(), "http://checker.test")},
        bus=EventBus(tmp_path / "events.jsonl"),
        federation=FederationBridge(gms_url="http://127.0.0.1:9", platform="t"))

    result = await unified.execute(ExecuteRequest(
        capability="check.run", inputs={"subject": "x"}))
    decision = decide(result.status, result.verdicts, result.error)

    # `tests` passed but `build` did not run, and a hard gate that did not
    # pass refuses the vend — the honest answer for an unbuilt artifact.
    assert decision.accepted is False
    assert decision.hard_passed == 1 and decision.hard_failed == 1


async def test_a_directory_artifact_becomes_a_browsable_listing(tmp_path):
    """A path printed at a reader is not a deliverable. The tree is what turns
    a generated project into something a visitor can actually open."""
    root = tmp_path / "engine"
    (root / "proj" / "app").mkdir(parents=True)
    (root / "proj" / "main.py").write_text("x = 1\n")
    (root / "proj" / "app" / "api.py").write_text("y = 2\n")
    (root / "proj" / "__pycache__").mkdir()
    (root / "proj" / "__pycache__" / "junk.pyc").write_bytes(b"\x00")

    remote = in_process_remote(Producer(root), "http://producer.test")
    got = await remote.artifact_tree(str(root / "proj"))
    paths = [f["path"] for f in got["files"]]
    assert paths == ["app/api.py", "main.py"]
    # Build noise is not part of what was made.
    assert not any("__pycache__" in p for p in paths)


async def test_the_tree_honours_the_same_boundary_as_the_file_route(tmp_path):
    root = tmp_path / "engine"
    root.mkdir(parents=True)
    (tmp_path / "elsewhere").mkdir()

    remote = in_process_remote(Producer(root), "http://producer.test")
    r = await remote._client.get("/artifacts/tree",
                                 params={"path": str(tmp_path / "elsewhere")})
    assert r.status_code == 404


async def test_a_single_file_artifact_is_readable_by_its_own_name(tmp_path):
    """The tree lists a single-file artifact as one entry named after itself,
    so a client naturally asks for path=<the file>&rel=<its name>. Joining
    those would build `report.md/report.md`. Asking for the only file in an
    artifact must return that file."""
    root = tmp_path / "engine"
    root.mkdir(parents=True)
    report = root / "session_1.md"
    report.write_text("# Findings\n")

    remote = in_process_remote(Producer(root), "http://producer.test")
    tree = await remote.artifact_tree(str(report))
    assert [f["path"] for f in tree["files"]] == ["session_1.md"]

    got = await remote.artifact_file(str(report), "session_1.md")
    assert got["text"] == "# Findings\n"
    # …and without the redundant rel, which must behave identically.
    assert (await remote.artifact_file(str(report)))["text"] == "# Findings\n"


async def test_an_objectives_verdicts_survive_the_process_that_made_them(tmp_path):
    """An objective is rebuilt from the event log, so anything living only in
    the returned result dies with the process. Artifact paths learned that
    lesson already; verdicts had the same hole — a run inspected after a
    restart showed an empty panel and looked unchecked."""
    from entropy_os.composition.events.bus import EventBus
    from entropy_os.composition.federation.datahub import FederationBridge
    from entropy_os.composition.orchestration.runtime import run_and_record_stage
    from entropy_os.composition.orchestration.stages import PlannedStage

    bus = EventBus(tmp_path / "events.jsonl")
    member = in_process_remote(Checker(), "http://checker.test")
    stage = PlannedStage(seq=1, engine="checker", capability="check.run",
                         make_inputs=lambda inputs, acc: {"subject": "x"})

    await run_and_record_stage(
        member, stage, "obj-test", "", {"subject": "x"}, {},
        bus, FederationBridge(gms_url="http://127.0.0.1:9", platform="t"),
        "", "inline", "unified")

    # Read them back the way the front door does: off the log, not memory.
    replayed = [e for e in bus.recent(limit=100)
                if e.kind == "StageCompleted" and e.objective_id == "obj-test"]
    assert replayed, "the stage was not recorded at all"
    verdicts = [v for e in replayed for v in (e.payload.get("verdicts") or [])]
    gates = {v["gate"] for v in verdicts}
    assert gates == {"tests", "reviewer", "build"}
    assert {v["determinism"] for v in verdicts} == {"hard", "soft"}
