"""The deterministic scaffold: the engines propose, the scaffold decides.

The claim under test is not "gates exist" — it is that the composition
boundary makes a real decision, deterministically, from facts the contract
already recorded, and that it stops a run rather than building on a result
the gates rejected.
"""

from __future__ import annotations

from entropy_os.composition.contract import ExecuteRequest, ExecuteResult, SemanticEvent
from entropy_os.composition.scaffold import (
    CurriculumIsOrdered,
    Determinism,
    EvidenceFloor,
    ProducedSomething,
    ReviewFloor,
    StageSucceeded,
    VerificationPassed,
)
from entropy_os.composition.scaffold.verdict import GateVerdict, StageJudgment

from .conftest import in_process_remote

# --------------------------------------------------------------------------- #
# verdicts and consequence policy
# --------------------------------------------------------------------------- #

def _verdict(passed: bool, determinism: Determinism) -> GateVerdict:
    return GateVerdict(gate="g", determinism=determinism, passed=passed,
                       evidence="because")


def test_consequence_follows_from_how_the_call_was_judged():
    """A failing gate escalates by its determinism: a hard fact stops the run,
    a human-tier check pauses for a person, an opinion is recorded only."""
    assert _verdict(True, Determinism.HARD).action == "proceed"
    assert _verdict(False, Determinism.HARD).action == "block"
    assert _verdict(False, Determinism.HUMAN).action == "hold"
    # The rule that keeps a SOFT gate from quietly becoming a hard one.
    assert _verdict(False, Determinism.SOFT).action == "proceed"


def test_the_strictest_verdict_wins_regardless_of_order():
    """A run must not proceed because a lenient gate happened to run last."""
    strict_last = StageJudgment(stage_seq=1, engine="e", verdicts=[
        _verdict(True, Determinism.HARD), _verdict(False, Determinism.HARD)])
    strict_first = StageJudgment(stage_seq=1, engine="e", verdicts=[
        _verdict(False, Determinism.HARD), _verdict(True, Determinism.HARD)])
    assert strict_last.action == strict_first.action == "block"

    mixed = StageJudgment(stage_seq=1, engine="e", verdicts=[
        _verdict(False, Determinism.HUMAN), _verdict(False, Determinism.SOFT)])
    assert mixed.action == "hold"


def test_no_gates_means_no_obstruction():
    assert StageJudgment(stage_seq=1, engine="e").action == "proceed"


# --------------------------------------------------------------------------- #
# the gates themselves — pure functions of what the contract recorded
# --------------------------------------------------------------------------- #

def test_gates_carry_evidence_not_bare_booleans():
    """A decision nobody can re-check is an assertion, not a decision."""
    result = ExecuteResult(status="completed",
                           outputs={"entities": 0, "claims": 0})
    verdict = EvidenceFloor().evaluate(result, 1, "research")
    assert verdict.passed is False
    assert "0 entities, 0 claims" in verdict.evidence
    assert verdict.facts == {"entities": 0, "claims": 0}
    assert verdict.determinism is Determinism.HARD


def test_evidence_floor_catches_a_quiet_research_failure():
    """A research session returning nothing has not failed loudly — and a
    curriculum built on it would be the model's prior, not a discovery."""
    empty = ExecuteResult(status="completed", outputs={"session_id": "s1"})
    grounded = ExecuteResult(status="completed",
                             outputs={"entities": 12, "claims": 30})
    assert EvidenceFloor().evaluate(empty).passed is False
    assert EvidenceFloor().evaluate(grounded).passed is True


def test_produced_something_rejects_a_silent_success():
    nothing = ExecuteResult(status="completed", outputs={"note": "hi"})
    something = ExecuteResult(status="completed", outputs={"project_id": "p1"})
    assert ProducedSomething().evaluate(nothing).passed is False
    assert ProducedSomething().evaluate(something).passed is True


def test_stage_succeeded_reports_the_engines_own_error():
    failed = ExecuteResult(status="failed", error="boom in the engine")
    verdict = StageSucceeded().evaluate(failed)
    assert verdict.passed is False
    assert "boom in the engine" in verdict.evidence


def test_curriculum_gate_wants_an_actual_order():
    thin = ExecuteResult(status="completed", outputs={"learning_order": ["a"]})
    real = ExecuteResult(status="completed",
                         outputs={"learning_order": ["a", "b", "c"]})
    assert CurriculumIsOrdered().evaluate(thin).passed is False
    assert CurriculumIsOrdered().evaluate(real).passed is True


def test_review_floor_reads_the_engines_own_agents():
    low = ExecuteResult(status="completed",
                        outputs={"scores": {"Design Agent": 40.0}})
    fine = ExecuteResult(status="completed",
                         outputs={"scores": {"Design Agent": 92.0}})
    verdict = ReviewFloor().evaluate(low)
    assert verdict.passed is False and "Design Agent" in verdict.evidence
    assert ReviewFloor().evaluate(fine).passed is True
    # No scores at all is a failure, not a pass by absence.
    assert ReviewFloor().evaluate(
        ExecuteResult(status="completed", outputs={})).passed is False


def test_verification_gate_is_human_tier_on_purpose():
    """Whether the suite is red is a hard fact the gate settles; whether to
    continue anyway is a judgment a person makes."""
    red = ExecuteResult(
        status="completed", outputs={"verification_passed": False},
        events=[SemanticEvent(kind="SoftwareVerificationFailed",
                              payload={"known_problems": ["pytest: boom"]})])
    verdict = VerificationPassed().evaluate(red, 3, "software")
    assert verdict.passed is False
    assert verdict.determinism is Determinism.HUMAN
    assert verdict.action == "hold"          # pauses, does not silently stop
    assert "pytest: boom" in verdict.evidence


# --------------------------------------------------------------------------- #
# the scaffold in a running composition
# --------------------------------------------------------------------------- #

async def test_a_blocked_gate_stops_the_run_before_the_next_stage(unified,
                                                                  members):
    """The point of the whole exercise: a rejected result must not become the
    input to downstream work."""
    from .conftest import FakeResearch

    class GroundlessResearch(FakeResearch):
        entities = 0
        claims = 0

    unified.members["research"] = in_process_remote(GroundlessResearch(),
                                                    "http://g.test")
    result = await unified.execute(ExecuteRequest(
        capability="compose.learning_platform", inputs={"topic": "Ghost"}))

    assert result.status == "failed"
    assert "evidence_floor" in result.error
    # Only research ran. The curriculum was never asked to build on nothing.
    assert len(result.provenance.children) == 1


async def test_the_verification_gate_holds_the_run_a_real_flagship_case(
        unified, members):
    """The first flagship run shipped software with a failing test suite and
    a website was generated for it anyway. With the scaffold in place that
    result is held instead — inline, where no human is reachable, holding
    means stopping and saying so."""
    from .conftest import FakeSoftware

    class RedSuite(FakeSoftware):
        async def _run(self, req, emit, vouch):
            outputs, artifacts, urns, notes = await super()._run(req, emit, vouch)
            outputs["verification_passed"] = False
            emit("SoftwareVerificationFailed",
                 known_problems=["pytest: test_quiz_service AttributeError"])
            return outputs, artifacts, urns, notes

    unified.members["software"] = in_process_remote(RedSuite(),
                                                    "http://red.test")
    result = await unified.execute(ExecuteRequest(
        capability="compose.learning_platform", inputs={"topic": "WebGPU"}))

    assert result.status == "failed"
    assert "verification_passed" in result.error
    assert "needs a human decision" in result.error
    # research, curriculum, software ran — the WEB stage did not.
    assert len(result.provenance.children) == 3
    assert [c.engine for c in result.provenance.children][-1] == "fake-software"


async def test_every_decision_is_published_as_a_fact(unified, bus):
    """A verdict nobody can find later is a log line, not governance."""
    await unified.execute(ExecuteRequest(
        capability="compose.learning_platform", inputs={"topic": "Rust"}))

    judged = [e for e in bus.recent() if e.kind == "GatesEvaluated"]
    assert len(judged) == 4, "one judgment per stage"
    assert all(e.payload["decision"] == "proceed" for e in judged)

    software = next(e for e in judged if e.payload["engine"] == "software")
    gates = {v["gate"]: v for v in software.payload["verdicts"]}
    assert set(gates) == {"stage_succeeded", "produced_something",
                          "verification_passed"}
    # Determinism is recorded honestly alongside the verdict.
    assert gates["verification_passed"]["determinism"] == "human"
    assert gates["stage_succeeded"]["determinism"] == "hard"


def test_gates_need_nothing_but_a_contract_result():
    """The scaffold adds decision without adding coupling.

    Every gate declared by every pipeline must reach a verdict from a bare
    ExecuteResult alone — no engine object, no adapter, no network. That is
    what lets an engine which joins later be judged by the same gates without
    either side knowing about the other."""
    from entropy_os.composition.orchestration.stages import COMPOSED_PIPELINES

    bare = ExecuteResult(status="completed")
    checked = 0
    for pipeline in COMPOSED_PIPELINES.values():
        for stage in pipeline.stages:
            gates = stage.resolved_gates()
            assert gates, f"stage {stage.seq} of {pipeline.name} ungated"
            for gate in gates:
                verdict = gate.evaluate(bare, stage.seq, stage.engine)
                # A verdict is always reachable, always attributed, and always
                # carries its reasoning.
                assert verdict.gate == gate.name
                assert verdict.evidence
                assert verdict.determinism in set(Determinism)
                checked += 1
    assert checked >= 8, "expected gates on every pipeline stage"


def test_determinism_is_declared_honestly():
    """Only a person's sign-off may claim HUMAN, and only a recorded fact may
    claim HARD. A gate that reads a boolean the engine computed is HARD; the
    one that asks a person to accept a known defect is HUMAN."""
    assert StageSucceeded.determinism is Determinism.HARD
    assert EvidenceFloor.determinism is Determinism.HARD
    assert ReviewFloor.determinism is Determinism.HARD
    assert VerificationPassed.determinism is Determinism.HUMAN
    # Nothing in the composition layer claims to be an opinion, because by
    # the time a result reaches here the engines have already converted their
    # opinions into recorded facts.
    from entropy_os.composition.orchestration.stages import COMPOSED_PIPELINES
    used = {g.determinism
            for p in COMPOSED_PIPELINES.values()
            for s in p.stages for g in s.resolved_gates()}
    assert Determinism.SOFT not in used


def test_the_workflow_import_graph_stays_free_of_io():
    """Composition gates run inside the Temporal workflow sandbox, which
    refuses non-deterministic access. That makes the *import graph* of the
    modules a workflow touches part of the design, not an implementation
    detail.

    This caught a real layering mistake: a gate reached for `identifying()`
    from the federation package, whose __init__ imports httpx — dragging
    urllib into the sandbox. The convention moved to the contract, which is a
    dependency-free leaf. This test is the guard that keeps it there.
    """
    import subprocess
    import sys

    probe = (
        "import sys, importlib;"
        "importlib.import_module('entropy_os.composition.orchestration.stages');"
        "importlib.import_module('entropy_os.composition.scaffold');"
        "bad = sorted(m for m in sys.modules if m.split('.')[0] in "
        "{'httpx','urllib','socket','ssl','requests','http'});"
        "print(','.join(bad))"
    )
    # A subprocess, because sys.modules in this process is already polluted
    # by every other test's imports.
    out = subprocess.run([sys.executable, "-c", probe],
                         capture_output=True, text=True, check=True)
    pulled = [m for m in out.stdout.strip().split(",") if m]
    assert not pulled, (
        f"the workflow's import graph pulls in I/O modules: {pulled}. "
        "Anything a gate imports must be free of I/O, or the Temporal "
        "sandbox will refuse it at runtime.")


# --------------------------------------------------------------------------- #
# one engine or all four — the same bar
# --------------------------------------------------------------------------- #

async def test_one_engine_alone_faces_the_same_gates_as_a_stage(unified):
    """one-engine runs ONE engine or ALL of them depending on what is asked.
    A capability is judged by what it produced, not by how it was invoked, so
    a direct call must not ship what a composed run would hold."""
    from .conftest import FakeSoftware

    class RedSuite(FakeSoftware):
        async def _run(self, req, emit, vouch):
            outputs, artifacts, urns, notes = await super()._run(req, emit, vouch)
            outputs["verification_passed"] = False
            emit("SoftwareVerificationFailed", known_problems=["pytest: boom"])
            return outputs, artifacts, urns, notes

    unified.members["software"] = in_process_remote(RedSuite(),
                                                    "http://red.test")

    # Asked for on its own — a single-engine vend.
    direct = await unified.execute(ExecuteRequest(
        capability="software.build", inputs={"request": "a thing"}))
    assert direct.status == "failed"
    assert "verification_passed" in direct.error

    # The same engine, the same failure, reached as stage 3 of a composition.
    composed = await unified.execute(ExecuteRequest(
        capability="compose.learning_platform", inputs={"topic": "WebGPU"}))
    assert composed.status == "failed"
    assert "verification_passed" in composed.error


async def test_a_single_engine_vend_still_passes_when_it_is_good(unified):
    """The gate is a bar, not a blockade: a healthy single-engine run goes
    through untouched, which is what keeps a one-capability vend fast."""
    result = await unified.execute(ExecuteRequest(
        capability="web.generate_site", inputs={"request": "a site"}))
    assert result.status == "completed"
    assert result.outputs["project_id"] == "w1"


async def test_a_direct_call_publishes_its_verdict_too(unified, bus):
    """Governance does not depend on which door the work came through."""
    await unified.execute(ExecuteRequest(
        capability="research.investigate", inputs={"topic": "Zig"}))
    judged = [e for e in bus.recent() if e.kind == "GatesEvaluated"]
    assert len(judged) == 1
    gates = {v["gate"] for v in judged[0].payload["verdicts"]}
    assert gates == {"stage_succeeded", "produced_something", "evidence_floor"}
    assert judged[0].payload["decision"] == "proceed"


def test_one_table_governs_both_paths():
    """Stages resolve their gates from the capability policy rather than
    re-declaring them, so a composed pipeline and a direct call cannot drift
    apart — the drift being the whole bug this guards against."""
    from entropy_os.composition.orchestration.stages import COMPOSED_PIPELINES
    from entropy_os.composition.scaffold import gates_for

    for pipeline in COMPOSED_PIPELINES.values():
        for stage in pipeline.stages:
            assert stage.gates is None, (
                f"{pipeline.name} stage {stage.seq} overrides its capability's "
                "gates; that is allowed but should be deliberate")
            resolved = {g.name for g in stage.resolved_gates()}
            policy = {g.name for g in gates_for(stage.capability)}
            assert resolved == policy
