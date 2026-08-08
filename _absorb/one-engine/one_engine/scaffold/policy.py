"""Which gates judge which capability — stated once, for every path.

A capability is judged by what it produced, not by how it was invoked. Asking
one-engine for `software.build` directly and getting it as stage 3 of a
composed objective are the same work, so they must face the same bar.

Without this registry the two paths drift, and the drift is perverse: a
composed run holds a red test suite for a human, while the identical direct
call ships it silently. Same engine, same failure, different consequence
depending on how you asked.

So gates live here, keyed by capability, and every path resolves them from
this one table:

  * a composed pipeline's stage, unless it deliberately overrides them;
  * a direct atomic call through the composite;
  * a second-level system delegating either of the above.

A capability absent from this table is ungated — deliberately possible (a
read-only or trivial capability need not be judged), and visible as absence
rather than hidden as an accident.
"""

from __future__ import annotations

from .gates import (
    CompositionGate,
    CurriculumIsOrdered,
    EvidenceFloor,
    ProducedSomething,
    ReviewFloor,
    StageSucceeded,
    VerificationPassed,
)

# Every judged capability starts from the same two floors — it ran, and it
# produced something identifiable — then adds whatever its domain makes
# checkable.
_FLOOR: tuple[CompositionGate, ...] = (StageSucceeded(), ProducedSomething())

CAPABILITY_GATES: dict[str, tuple[CompositionGate, ...]] = {
    "research.investigate": (*_FLOOR, EvidenceFloor()),
    "university.design_curriculum": (*_FLOOR, CurriculumIsOrdered()),
    "software.build": (*_FLOOR, VerificationPassed()),
    "web.generate_site": (*_FLOOR, ReviewFloor()),
    # The teaching loop's other capabilities are steps inside a session rather
    # than artifacts: next_activity/assess/finish_session are judged by the
    # engine's own mastery evidence, and adding a composition gate over them
    # would be inventing a bar rather than reading one.
}


def gates_for(capability: str) -> tuple[CompositionGate, ...]:
    """The gates that judge a capability, wherever it is invoked from."""
    return CAPABILITY_GATES.get(capability, ())
