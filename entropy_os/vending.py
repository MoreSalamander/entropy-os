"""What a vended slot is, and what makes one acceptable.

The Vending Machine used to call four studios in this process. It now calls
engines through the Universal Engine Contract, which changes where the work
happens and nothing about who decides whether the work is good: the engines
propose, and the rule below decides.

That rule is Veritas doctrine, stated once, as a function of what an engine
reported about itself:

    accept  ⇐  at least one HARD verdict passed
           AND every HARD verdict passed

Both halves matter, and the first is the one that gets forgotten. An engine
that ran no hard checks has proven nothing; "no failures" is not the same
claim as "it was checked", and a machine that treated silence as success
would be at its most confident exactly when it knew least. SOFT verdicts —
a judge model's opinion — can inform a reader and can never block or grant
acceptance. That is what makes the label worth printing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .composition.contract import Determinism

# Wedge slot → the capability that now serves it. The four studios these
# replaced were each defined by their verification model; the engines carry
# the same models, with their gates reported rather than summarised.
SLOT_CAPABILITY: dict[str, str] = {
    "software": "software.build",
    "research": "research.investigate",
    "learn": "university.design_curriculum",
    # A page and a whole site are the same engine at different scope; the
    # design engine plans its own pages from the brief.
    "web": "web.generate_site",
    "site": "web.generate_site",
}

# What each slot's capability wants its goal called.
SLOT_INPUT_FIELD: dict[str, str] = {
    "software": "request",
    "research": "topic",
    "learn": "goal",
    "web": "request",
    "site": "request",
}


@dataclass(frozen=True)
class Acceptance:
    """The verdict on a whole run, and the reasoning that produced it."""

    accepted: bool
    reason: str
    hard_passed: int = 0
    hard_failed: int = 0
    soft: int = 0
    verdicts: list[dict[str, Any]] = field(default_factory=list)


def as_evidence(verdicts: list[Any]) -> list[dict[str, Any]]:
    """Contract verdicts in the shape the tray has always rendered.

    Deliberately lossless about determinism: a reader must be able to see
    that a given line was a judge's opinion rather than a test result.
    """
    out: list[dict[str, Any]] = []
    for v in verdicts:
        determinism = v.determinism.value if hasattr(v.determinism, "value") else str(v.determinism)
        out.append({
            "gate": v.gate,
            "determinism": determinism,
            "passed": bool(v.passed),
            "evidence": v.evidence,
            "facts": dict(v.facts or {}),
        })
    return out


def decide(status: str, verdicts: list[Any], error: str = "") -> Acceptance:
    """Apply the acceptance rule to one engine result.

    `status` is the engine's own report of whether it finished. A run that
    crashed is not acceptable no matter what it managed to check first —
    though those checks are still reported, because they are still true.
    """
    evidence = as_evidence(verdicts)
    hard = [v for v in evidence if v["determinism"] == Determinism.HARD.value]
    hard_passed = [v for v in hard if v["passed"]]
    hard_failed = [v for v in hard if not v["passed"]]
    soft = [v for v in evidence if v["determinism"] != Determinism.HARD.value]

    def result(accepted: bool, reason: str) -> Acceptance:
        return Acceptance(accepted=accepted, reason=reason,
                          hard_passed=len(hard_passed), hard_failed=len(hard_failed),
                          soft=len(soft), verdicts=evidence)

    if status != "completed":
        return result(False, error or "the engine did not complete the run")
    if not hard:
        # The rule that keeps an unchecked run from looking like a clean one.
        return result(False,
                      "no hard gate ran, so nothing was proven — an unchecked "
                      "run is not an accepted one")
    if hard_failed:
        names = ", ".join(v["gate"] for v in hard_failed[:4])
        return result(False, f"hard gate(s) failed: {names}")
    return result(True,
                  f"{len(hard_passed)} hard gate(s) passed"
                  + (f", {len(soft)} advisory finding(s) recorded" if soft else ""))
