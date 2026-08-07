"""Typed vocabulary of the learning system.

The evidence chain for education:

    Concept --(requires/builds_upon/…)--> Concept       (the knowledge DAG)
    LearnerProfile holds MasteryState per concept
    MasteryState is DERIVED from Evidence rows (graded interactions)
    Activities produce Evidence; the adaptive policy reads mastery + schedule

Nothing in the learner model is set by prose — every state change traces to
a graded interaction.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from enum import Enum

from pydantic import BaseModel, Field


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


# --------------------------------------------------------------------------
# knowledge structure
# --------------------------------------------------------------------------

class EduRelation(str, Enum):
    REQUIRES = "requires"
    BUILDS_UPON = "builds_upon"
    RELATED_TO = "related_to"
    APPLIED_IN = "applied_in"
    EXPLAINS = "explains"
    CONTRASTS_WITH = "contrasts_with"
    DISCOVERED_BY = "discovered_by"


class Concept(BaseModel):
    id: str = Field(default_factory=lambda: new_id("con"))
    name: str
    subject: str = ""                 # e.g. "machine learning", "mathematics"
    summary: str = ""
    depth: int = 0                    # 0=goal-level, higher = deeper prerequisite


class LearningResource(BaseModel):
    id: str = Field(default_factory=lambda: new_id("res"))
    concept_name: str
    kind: str                         # paper | explanation | project | history | industry
    title: str
    url: str
    note: str = ""
    agent: str = ""                   # which research agent found it


# --------------------------------------------------------------------------
# learner model
# --------------------------------------------------------------------------

class Mastery(str, Enum):
    UNKNOWN = "unknown"
    INTRODUCED = "introduced"         # saw a lesson
    PRACTICING = "practicing"         # some correct evidence
    MASTERED = "mastered"             # rubric satisfied

# review intervals per mastery level (spaced repetition, deterministic)
REVIEW_INTERVALS = {Mastery.INTRODUCED: timedelta(days=1),
                    Mastery.PRACTICING: timedelta(days=3),
                    Mastery.MASTERED: timedelta(days=21)}

# mastery rubric constants — documented, testable
PROMOTE_TO_PRACTICING_CORRECT = 1     # ≥1 correct graded item
PROMOTE_TO_MASTERED_STREAK = 3        # last 3 graded items correct…
PROMOTE_TO_MASTERED_KINDS = 2         # …spanning ≥2 distinct item kinds
DEMOTE_ON_WRONG_STREAK = 2            # 2 consecutive misses drops a level


class EvidenceRow(BaseModel):
    at: datetime = Field(default_factory=now_utc)
    activity_id: str = ""
    item_kind: str = ""               # mcq | numeric | code | free_text | recall
    correct: bool = False
    weight: float = 1.0               # free_text judged by LLM carries 0.5
    method: str = ""                  # which teaching method preceded this
    detail: str = ""


class MasteryState(BaseModel):
    concept_name: str
    level: Mastery = Mastery.UNKNOWN
    evidence: list[EvidenceRow] = Field(default_factory=list)
    last_activity: datetime | None = None
    misconceptions: list[str] = Field(default_factory=list)

    @property
    def review_due(self) -> datetime | None:
        if self.level == Mastery.UNKNOWN or self.last_activity is None:
            return None
        return self.last_activity + REVIEW_INTERVALS[self.level]


class TeachingMethodStats(BaseModel):
    """Phase 9 memory: which method precedes success for THIS learner."""
    method: str
    attempts: int = 0
    successes: int = 0

    @property
    def rate(self) -> float | None:
        return round(self.successes / self.attempts, 2) if self.attempts else None


class LearnerProfile(BaseModel):
    id: str = Field(default_factory=lambda: new_id("learner"))
    name: str = "learner"
    goals: list[str] = Field(default_factory=list)
    mastery: dict[str, MasteryState] = Field(default_factory=dict)
    method_stats: dict[str, TeachingMethodStats] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=now_utc)

    def state(self, concept_name: str) -> MasteryState:
        key = concept_name.casefold()
        if key not in self.mastery:
            self.mastery[key] = MasteryState(concept_name=concept_name)
        return self.mastery[key]

    def mastered(self) -> list[str]:
        return [s.concept_name for s in self.mastery.values()
                if s.level == Mastery.MASTERED]


# --------------------------------------------------------------------------
# roadmap / curriculum
# --------------------------------------------------------------------------

class Roadmap(BaseModel):
    id: str = Field(default_factory=lambda: new_id("map"))
    goal: str
    subject: str = ""
    concepts: list[Concept] = Field(default_factory=list)
    edges: list[tuple[str, str, str]] = Field(default_factory=list)  # (src, relation, dst) by name
    validation_notes: list[str] = Field(default_factory=list)
    learning_order: list[str] = Field(default_factory=list)          # topological, prerequisites first


# --------------------------------------------------------------------------
# activities
# --------------------------------------------------------------------------

class ExerciseKind(str, Enum):
    MCQ = "mcq"
    NUMERIC = "numeric"
    CODE = "code"
    FREE_TEXT = "free_text"


class Exercise(BaseModel):
    id: str = Field(default_factory=lambda: new_id("ex"))
    concept_name: str
    kind: ExerciseKind
    prompt: str
    options: list[str] = Field(default_factory=list)   # mcq
    answer: str = ""                  # mcq letter / numeric value / expected stdout
    starter_code: str = ""            # code
    reference_solution: str = ""      # code — executed at generation time
    rubric: str = ""                  # free_text judge rubric
    verified: bool = False            # code items: reference reproduced answer


class Lesson(BaseModel):
    id: str = Field(default_factory=lambda: new_id("les"))
    concept_name: str
    method: str                       # teacher | socratic
    body_md: str
    mermaid: str = ""                 # concept-map diagram
    resources: list[LearningResource] = Field(default_factory=list)
    exercises: list[Exercise] = Field(default_factory=list)


class ActivityKind(str, Enum):
    LESSON = "lesson"
    PRACTICE = "practice"
    ASSESSMENT = "assessment"
    REVIEW = "review"


class Activity(BaseModel):
    id: str = Field(default_factory=lambda: new_id("act"))
    kind: ActivityKind
    concept_name: str
    reason: str                       # WHY the policy chose this — always stated
    lesson: Lesson | None = None
    exercises: list[Exercise] = Field(default_factory=list)


class GradedAnswer(BaseModel):
    exercise_id: str
    correct: bool
    weight: float
    feedback: str = ""
    misconception: str = ""           # non-empty when a wrong answer reveals one
