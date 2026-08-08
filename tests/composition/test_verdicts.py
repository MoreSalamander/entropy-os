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
