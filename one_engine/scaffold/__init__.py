"""The deterministic scaffold at the composition boundary.

The engines propose; the scaffold decides. Inside an engine, an LLM proposes
an artifact and a gate decides whether it is acceptable. Here, whole engines
propose stage results and a gate decides whether the objective may continue.

Gates are pure functions of what the contract already records, so they add
decision without adding coupling.
"""

from .gates import (
                    CompositionGate,
                    CurriculumIsOrdered,
                    EvidenceFloor,
                    ProducedSomething,
                    ReviewFloor,
                    StageSucceeded,
                    VerificationPassed,
)
from .verdict import Action, Determinism, GateVerdict, StageJudgment

__all__ = ["Action", "CompositionGate", "CurriculumIsOrdered", "Determinism",
           "EvidenceFloor", "GateVerdict", "ProducedSomething", "ReviewFloor",
           "StageJudgment", "StageSucceeded", "VerificationPassed"]
