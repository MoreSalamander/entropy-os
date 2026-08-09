"""The acceptance rule, which is the only thing standing between a vend and
a lie. Every case here is one the doctrine names explicitly."""

from __future__ import annotations

from entropy_os.composition.contract import Determinism, Verdict
from entropy_os.vending import SLOT_CAPABILITY, SLOT_INPUT_FIELD, decide


def v(gate: str, determinism: Determinism, passed: bool, evidence: str = "e") -> Verdict:
    return Verdict(gate=gate, determinism=determinism, passed=passed, evidence=evidence)


def test_a_run_with_no_hard_gate_is_never_accepted():
    """The half of the rule that gets forgotten. An engine that checked
    nothing has proven nothing, and 'no failures' is a different claim from
    'it was checked' — this is the case where a naive surface is most
    confident precisely when it knows least."""
    a = decide("completed", [v("reviewer", Determinism.SOFT, True)])
    assert a.accepted is False
    assert "no hard gate" in a.reason
    # The opinion is still reported; it just cannot grant acceptance.
    assert a.soft == 1
    assert a.verdicts[0]["determinism"] == "soft"


def test_no_verdicts_at_all_is_not_acceptance():
    a = decide("completed", [])
    assert a.accepted is False
    assert a.hard_passed == 0


def test_one_passing_hard_gate_accepts():
    a = decide("completed", [v("pytest", Determinism.HARD, True, "12 passed")])
    assert a.accepted is True
    assert a.hard_passed == 1


def test_any_failing_hard_gate_refuses_however_many_passed():
    a = decide("completed", [
        v("ruff", Determinism.HARD, True),
        v("pytest", Determinism.HARD, False, "1 failed"),
        v("security", Determinism.HARD, True),
    ])
    assert a.accepted is False
    assert "pytest" in a.reason
    assert (a.hard_passed, a.hard_failed) == (2, 1)


def test_a_soft_failure_never_blocks():
    """A judge model may flag; it may not veto. Otherwise an opinion has been
    promoted to proof through the back door."""
    a = decide("completed", [
        v("pytest", Determinism.HARD, True),
        v("reviewer", Determinism.SOFT, False, "disliked the naming"),
    ])
    assert a.accepted is True
    assert a.soft == 1


def test_a_human_verdict_does_not_count_as_a_hard_gate():
    """HUMAN is its own determinism for a reason: a person's sign-off is a
    different kind of claim from a machine check, and must not silently
    satisfy the machine-checked floor."""
    a = decide("completed", [v("operator", Determinism.HUMAN, True)])
    assert a.accepted is False
    assert "no hard gate" in a.reason


def test_a_crashed_run_is_refused_but_still_reports_what_it_checked():
    a = decide("failed", [v("ruff", Determinism.HARD, True)],
               error="generation crashed after linting")
    assert a.accepted is False
    assert a.reason == "generation crashed after linting"
    assert a.hard_passed == 1          # true, and still worth showing
    assert len(a.verdicts) == 1


def test_every_vendable_slot_maps_to_a_capability_and_an_input():
    """A slot the machine offers but cannot route is a 404 discovered by a
    paying visitor."""
    from entropy_os.wedge import VENDABLE_ORGS

    for slot in VENDABLE_ORGS:
        assert slot in SLOT_CAPABILITY, f"{slot} has no capability"
        assert slot in SLOT_INPUT_FIELD, f"{slot} has no input field"
