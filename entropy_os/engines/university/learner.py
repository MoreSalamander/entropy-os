"""The learner model — mastery as a pure function of graded evidence.

Rubric (constants in models.py, tested in tests/test_learner.py):

  UNKNOWN     → INTRODUCED   completing a lesson activity
  INTRODUCED  → PRACTICING   ≥1 correct graded item
  PRACTICING  → MASTERED     last 3 graded items correct AND spanning
                             ≥2 distinct item kinds (breadth, not luck)
  any level   ↓ one level    2 consecutive misses (weighted items count
                             proportionally; an LLM-judged free-text answer
                             carries weight 0.5 — it can help, never
                             single-handedly promote)

Review scheduling is deterministic spaced repetition: due = last activity +
interval per level (1d / 3d / 21d). Method stats update per graded item so
the platform learns which teaching method precedes success for THIS learner.
"""

from __future__ import annotations

import json
from pathlib import Path

from .models import (DEMOTE_ON_WRONG_STREAK, PROMOTE_TO_MASTERED_KINDS,
                     PROMOTE_TO_MASTERED_STREAK, EvidenceRow, LearnerProfile,
                     Mastery, MasteryState, TeachingMethodStats, now_utc)

_ORDER = [Mastery.UNKNOWN, Mastery.INTRODUCED, Mastery.PRACTICING,
          Mastery.MASTERED]


def mark_introduced(state: MasteryState) -> None:
    if state.level == Mastery.UNKNOWN:
        state.level = Mastery.INTRODUCED
    state.last_activity = now_utc()


def apply_evidence(state: MasteryState, row: EvidenceRow) -> Mastery:
    """Append evidence, recompute level. Returns the (possibly new) level."""
    state.evidence.append(row)
    state.last_activity = row.at
    recent = state.evidence[-max(PROMOTE_TO_MASTERED_STREAK,
                                 DEMOTE_ON_WRONG_STREAK):]

    # demotion first: two consecutive full-weight misses
    misses = 0.0
    for r in reversed(state.evidence):
        if r.correct:
            break
        misses += r.weight
    if misses >= DEMOTE_ON_WRONG_STREAK:
        idx = _ORDER.index(state.level)
        if idx > 1:  # never demote below INTRODUCED (they did see the lesson)
            state.level = _ORDER[idx - 1]
        return state.level

    # promotion
    if state.level == Mastery.INTRODUCED:
        if any(r.correct for r in state.evidence):
            state.level = Mastery.PRACTICING
    if state.level == Mastery.PRACTICING:
        streak = state.evidence[-PROMOTE_TO_MASTERED_STREAK:]
        if (len(streak) == PROMOTE_TO_MASTERED_STREAK
                and all(r.correct for r in streak)
                and sum(r.weight for r in streak) >= PROMOTE_TO_MASTERED_STREAK - 0.5
                and len({r.item_kind for r in streak}) >= PROMOTE_TO_MASTERED_KINDS):
            state.level = Mastery.MASTERED
    return state.level


def record_method_outcome(profile: LearnerProfile, method: str,
                          success: bool) -> None:
    if not method:
        return
    stats = profile.method_stats.setdefault(
        method, TeachingMethodStats(method=method))
    stats.attempts += 1
    stats.successes += int(success)


def preferred_method(profile: LearnerProfile) -> str | None:
    """This learner's best-performing teaching method (≥2 attempts)."""
    best, best_rate = None, -1.0
    for stats in profile.method_stats.values():
        if stats.attempts >= 2 and (stats.rate or 0) > best_rate:
            best, best_rate = stats.method, stats.rate or 0
    return best


# --------------------------------------------------------------------------
# persistence — one JSON per learner, atomic (family pattern)
# --------------------------------------------------------------------------

def save_profile(profile: LearnerProfile, learners_dir: Path) -> Path:
    learners_dir.mkdir(parents=True, exist_ok=True)
    path = learners_dir / f"{profile.id}.json"
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(profile.model_dump_json(indent=2))
    tmp.replace(path)
    return path


def load_profile(learners_dir: Path, learner_id: str) -> LearnerProfile | None:
    path = learners_dir / f"{learner_id}.json"
    if not path.exists():
        return None
    return LearnerProfile.model_validate(json.loads(path.read_text()))
