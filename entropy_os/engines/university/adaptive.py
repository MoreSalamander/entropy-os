"""Phase 6 + 7 — the Adaptive Learning Engine.

`next_activity` is a deterministic decision tree over the learner model,
the roadmap order, and the review schedule — and it always STATES its
reason (every Activity carries `reason`):

  1. overdue review          spaced repetition beats everything
  2. confusion repair        a concept with a fresh misconception gets a
                             targeted re-teach (Socratic by default: make
                             them rebuild the idea)
  3. practice-in-progress    a PRACTICING concept close to mastery gets
                             more practice (streak needs breadth)
  4. next concept            first concept in learning_order not yet
                             PRACTICING — taught with the method this
                             learner (or the shared KG) responds to best
  5. done                    everything in the roadmap mastered

The spec's rule "never re-teach what is known" is rule 4's filter; the
Phase 7 hook decorates new-concept activities with cross-disciplinary
paths discovered in the KG.
"""

from __future__ import annotations

from .graphs.knowledge_graph import EducationKnowledgeGraph
from .learner import preferred_method
from .models import Activity, ActivityKind, LearnerProfile, Mastery, Roadmap, now_utc


def next_activity(profile: LearnerProfile, roadmap: Roadmap,
                  kg: EducationKnowledgeGraph) -> Activity | None:
    now = now_utc()
    states = {s.concept_name: s for s in
              (profile.state(name) for name in roadmap.learning_order)}

    # 1 — overdue reviews, most overdue first
    overdue = [(s.review_due, name) for name, s in states.items()
               if s.review_due and s.review_due <= now
               and s.level != Mastery.UNKNOWN]
    if overdue:
        due, name = sorted(overdue)[0]
        return Activity(kind=ActivityKind.REVIEW, concept_name=name,
                        reason=f"review due since {due:%Y-%m-%d %H:%M} "
                               f"(spaced repetition, level "
                               f"{states[name].level.value})")

    # 2 — freshest misconception gets a repair lesson
    for name in roadmap.learning_order:
        s = states[name]
        if s.misconceptions and s.level in (Mastery.INTRODUCED,
                                            Mastery.PRACTICING):
            return Activity(kind=ActivityKind.LESSON, concept_name=name,
                            reason=f"repairing misconception: "
                                   f"“{s.misconceptions[-1][:80]}” "
                                   "(Socratic re-teach)")

    # 3 — practicing concepts continue until the mastery rubric is met
    for name in roadmap.learning_order:
        if states[name].level == Mastery.PRACTICING:
            return Activity(kind=ActivityKind.PRACTICE, concept_name=name,
                            reason="practicing: mastery rubric needs a "
                                   "3-streak across ≥2 item kinds")

    # 4 — the next not-yet-learned concept, prerequisites first by order
    for name in roadmap.learning_order:
        s = states[name]
        if s.level in (Mastery.UNKNOWN, Mastery.INTRODUCED):
            kind = (ActivityKind.PRACTICE if s.level == Mastery.INTRODUCED
                    else ActivityKind.LESSON)
            reason = ("introduced but unpracticed — evidence needed"
                      if s.level == Mastery.INTRODUCED else
                      f"next in prerequisite order (position "
                      f"{roadmap.learning_order.index(name) + 1}"
                      f"/{len(roadmap.learning_order)})")
            act = Activity(kind=kind, concept_name=name, reason=reason)
            # Phase 7 decoration: bridges from what they know
            paths = kg.cross_disciplinary(profile.mastered(), name)
            if paths:
                act.reason += (" | cross-disciplinary bridge: "
                               + " → ".join(paths[0]))
            return act

    return None  # roadmap fully mastered


def choose_method(profile: LearnerProfile, kg: EducationKnowledgeGraph,
                  concept: str, repairing: bool = False) -> str:
    """Socratic for misconception repair; otherwise this learner's proven
    method, else the shared KG's best for the concept, else teacher."""
    if repairing:
        return "socratic"
    return (preferred_method(profile)
            or kg.best_method_for(concept)
            or "teacher")
