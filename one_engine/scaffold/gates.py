"""The behavior side of the deterministic scaffold — composition gates.

A composition gate is a pure function from a stage's contract result to a
verdict. It is the only thing in a composed run allowed to say whether the run
may continue.

Two properties make these gates worth having, and both come from where they
sit rather than from how clever they are:

**They are almost entirely HARD.** The composition boundary is where
deterministic judgment is *most* available, because the engines already did
the hard part: research ran an evidence gate, code-engine ran ruff and pytest,
design-engine ran its review agents. By the time a result reaches here, the
opinions have already been converted into recorded facts — booleans, counts,
scores. A gate here reads facts; it does not form opinions.

**They read only the contract.** A gate touches `ExecuteResult.outputs`,
`.events`, and `.provenance` — never an engine's internals. That is what keeps
the scaffold composable: an engine that joins later is judged by the same
gates without either side knowing about the other.

Because they are pure, gates are evaluated inside the Temporal workflow
itself. The decision is therefore made by the orchestrator, deterministically
and durably recorded — not inside an activity where it could be mistaken for
part of the engine's own work.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..contract import ExecuteResult, identifying
from .verdict import Determinism, GateVerdict


class CompositionGate(ABC):
    """Subclasses declare their determinism honestly and implement check()."""

    name: str
    determinism: Determinism

    @abstractmethod
    def check(self, result: ExecuteResult) -> tuple[bool, str, dict]:
        """Return (passed, evidence, facts). Evidence is prose a human can
        re-check; facts are the values the call was made on."""
        raise NotImplementedError

    def evaluate(self, result: ExecuteResult, stage_seq: int = 0,
                 engine: str = "") -> GateVerdict:
        passed, evidence, facts = self.check(result)
        return GateVerdict(gate=self.name, determinism=self.determinism,
                           passed=passed, evidence=evidence, facts=facts,
                           stage_seq=stage_seq, engine=engine)


# --------------------------------------------------------------------------- #
# Gates over what the contract records
# --------------------------------------------------------------------------- #

class StageSucceeded(CompositionGate):
    """The stage itself completed. The floor beneath every other gate."""

    name = "stage_succeeded"
    determinism = Determinism.HARD

    def check(self, result: ExecuteResult):
        ok = result.status == "completed"
        return (ok,
                f"stage status is {result.status!r}"
                + ("" if ok else f": {result.error[:160]}"),
                {"status": result.status})


class ProducedSomething(CompositionGate):
    """The stage produced an identifiable artifact.

    A stage that completes without producing anything is not a success — it is
    a silent failure, and every downstream stage would build on nothing.
    """

    name = "produced_something"
    determinism = Determinism.HARD

    def check(self, result: ExecuteResult):
        produced = identifying(result.outputs)
        return (bool(produced),
                f"identifying outputs: {sorted(produced) or 'NONE'}",
                {"produced": sorted(produced)})


class EvidenceFloor(CompositionGate):
    """Research must have grounded something.

    A research session that returns no entities and no claims has not failed
    loudly — it has failed quietly, and a curriculum built on it would be the
    model's prior rather than anything discovered.
    """

    name = "evidence_floor"
    determinism = Determinism.HARD

    def __init__(self, min_entities: int = 1, min_claims: int = 1):
        self.min_entities = min_entities
        self.min_claims = min_claims

    def check(self, result: ExecuteResult):
        entities = int(result.outputs.get("entities", 0) or 0)
        claims = int(result.outputs.get("claims", 0) or 0)
        ok = entities >= self.min_entities and claims >= self.min_claims
        return (ok,
                f"{entities} entities, {claims} claims "
                f"(floor: {self.min_entities}/{self.min_claims})",
                {"entities": entities, "claims": claims})


class CurriculumIsOrdered(CompositionGate):
    """A roadmap must actually be a roadmap: concepts, in an order."""

    name = "curriculum_is_ordered"
    determinism = Determinism.HARD

    def __init__(self, min_concepts: int = 2):
        self.min_concepts = min_concepts

    def check(self, result: ExecuteResult):
        order = result.outputs.get("learning_order") or []
        ok = len(order) >= self.min_concepts
        return (ok,
                f"{len(order)} concepts in learning order "
                f"(floor: {self.min_concepts})",
                {"concepts": len(order)})


class VerificationPassed(CompositionGate):
    """Generated software passed its own verification.

    HUMAN on purpose, and the distinction matters: whether the suite is red is
    a hard, deterministic fact, and this gate establishes it without argument.
    Whether a run may continue *anyway* — because the failure is understood,
    or the site is wanted regardless — is a judgment call, and a person should
    make it. The gate settles the fact; the human decides the consequence.

    This is the gate the first flagship run needed and did not have: GPUcademy
    shipped `verification_passed: False`, and a public website was generated
    for it without anyone deciding that was acceptable.
    """

    name = "verification_passed"
    determinism = Determinism.HUMAN

    def check(self, result: ExecuteResult):
        passed = bool(result.outputs.get("verification_passed"))
        problems = [e.payload.get("known_problems")
                    for e in result.events
                    if e.kind == "SoftwareVerificationFailed"]
        return (passed,
                "verification passed" if passed else
                f"verification FAILED: {str(problems[:1])[:200] or 'no detail'}",
                {"verification_passed": passed,
                 "repair_rounds": result.outputs.get("repair_rounds", 0)})


class ReviewFloor(CompositionGate):
    """Generated sites must clear their own review agents' floor."""


    name = "review_floor"
    determinism = Determinism.HARD

    def __init__(self, floor: float = 70.0):
        self.floor = floor

    def check(self, result: ExecuteResult):
        scores = result.outputs.get("scores") or {}
        if not scores:
            return False, "no review scores recorded", {}
        low = {k: v for k, v in scores.items() if float(v) < self.floor}
        return (not low,
                f"lowest agent score "
                f"{min(float(v) for v in scores.values()):.0f} "
                f"(floor: {self.floor:.0f})"
                + (f"; below floor: {sorted(low)}" if low else ""),
                {"scores": {k: float(v) for k, v in scores.items()}})
