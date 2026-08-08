"""The data side of the deterministic scaffold.

Vocabulary converges deliberately with Veritas (`engine/artifact.py`), because
this is the same thesis one level up: **the engines propose, the scaffold
decides.** Inside an engine, an LLM proposes an artifact and a gate decides
whether it is acceptable. At the composition boundary, whole engines propose
stage results and a gate decides whether the objective may continue.

Two rules carried over verbatim, because they are what make a gate worth
anything:

  * A gate declares its determinism **honestly**. A judge's opinion is never
    dressed up as proof.
  * A verdict carries **evidence**, never a bare boolean. A decision nobody
    can re-check is not a decision, it is an assertion.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# Determinism and the verdict shape are CONTRACT vocabulary, not scaffold
# vocabulary. They were defined here first because gates between engines were
# the first place they were needed; now that an engine can report its own
# checks across the wire, the same words have to mean the same thing on both
# sides of the boundary. Restating them would eventually let them drift, and
# two subtly different definitions of "hard" is precisely the failure this
# vocabulary exists to prevent.
from ..contract import Determinism, Verdict

__all__ = ["Action", "Determinism", "GateVerdict", "Verdict"]


# What a failed gate DOES. The gate itself never chooses this — it reports a
# verdict, and the scaffold maps (determinism, passed) onto a consequence. That
# separation is deliberate: a gate that could choose its own consequence would
# be deciding policy, and policy belongs in one place.
Action = Literal["proceed", "hold", "block"]


class GateVerdict(Verdict):
    """One gate's judgment of one STAGE — a Verdict plus its place in a run.

    An engine's own verdict answers "did this check pass"; a composition-level
    gate verdict also has to answer "on which stage, from which engine",
    because at that level the same gate runs many times over one objective.
    """

    stage_seq: int = 0
    engine: str = ""
    # Filled by whatever RECORDS the verdict, not by the gate that reached it.
    # A gate is a pure function of facts, and a pure function has no business
    # reading a clock — this one runs inside the Temporal workflow sandbox,
    # where wall-clock access is a determinism violation and correctly
    # refused. The time a decision was recorded belongs to the recorder.
    checked_at: str = ""

    @property
    def action(self) -> Action:
        """Consequence policy, in one place.

        A passing gate never impedes anything. A failing one is escalated by
        how it was judged: a hard fact stops the run, a human-tier check pauses
        for a person, and an opinion is recorded but never gets to stop work on
        its own — that last rule is what keeps a SOFT gate from quietly
        becoming a hard one.
        """
        if self.passed:
            return "proceed"
        if self.determinism is Determinism.HARD:
            return "block"
        if self.determinism is Determinism.HUMAN:
            return "hold"
        return "proceed"


class StageJudgment(BaseModel):
    """Every gate's verdict on one stage, plus the resulting decision."""

    stage_seq: int
    engine: str
    verdicts: list[GateVerdict] = Field(default_factory=list)

    @property
    def action(self) -> Action:
        """The strictest consequence any gate reached. Deterministic, and
        order-independent: a run does not proceed because a lenient gate ran
        last."""
        actions = {v.action for v in self.verdicts}
        if "block" in actions:
            return "block"
        if "hold" in actions:
            return "hold"
        return "proceed"

    @property
    def failed(self) -> list[GateVerdict]:
        return [v for v in self.verdicts if not v.passed]

    def summary(self) -> str:
        if not self.verdicts:
            return "no gates declared"
        parts = [f"{v.gate}={'pass' if v.passed else 'FAIL'}"
                 for v in self.verdicts]
        return ", ".join(parts)
