"""Phase 3 — Student Context Graph: the learner's current state, live.

Tracks the session as it happens: current activity, active concepts,
confusion points (wrong answers + logged misconceptions), goals, recent
interactions, and the mastery snapshot. Persisted per learner+session so
the API and the adaptive policy read one truthful model.
"""

from __future__ import annotations

import json
from pathlib import Path

import networkx as nx

from ..models import Activity, GradedAnswer, LearnerProfile, Roadmap, new_id, now_utc


class StudentContextGraph:
    def __init__(self, session_id: str, learner: LearnerProfile,
                 roadmap: Roadmap):
        self.session_id = session_id
        self.learner = learner
        self.roadmap = roadmap
        self.g = nx.MultiDiGraph()
        self.interactions: list[dict] = []
        self.confusion_points: list[dict] = []
        self.current_activity: Activity | None = None
        self.g.add_node("learner", kind="learner", label=learner.name)
        self.g.add_node("goal", kind="goal", label=roadmap.goal)
        self.g.add_edge("learner", "goal", key="pursues", kind="pursues")
        for c in roadmap.concepts:
            self.g.add_node(f"concept:{c.name}", kind="concept", label=c.name,
                            depth=c.depth)
        for s, rel, d in roadmap.edges:
            self.g.add_edge(f"concept:{s}", f"concept:{d}", key=rel, kind=rel)

    # ------------------------------------------------------------------ #
    def begin_activity(self, activity: Activity) -> None:
        self.current_activity = activity
        self.g.add_node(activity.id, kind="activity",
                        label=f"{activity.kind.value}: {activity.concept_name}",
                        reason=activity.reason)
        self.g.add_edge("learner", activity.id, key="doing", kind="doing")
        self.g.add_edge(activity.id, f"concept:{activity.concept_name}",
                        key="targets", kind="targets")
        self.interactions.append({"at": now_utc().isoformat(),
                                  "event": "activity_started",
                                  "activity": activity.kind.value,
                                  "concept": activity.concept_name,
                                  "reason": activity.reason})

    def record_answer(self, concept: str, graded: GradedAnswer) -> None:
        self.interactions.append({"at": now_utc().isoformat(),
                                  "event": "answer",
                                  "concept": concept,
                                  "correct": graded.correct,
                                  "feedback": graded.feedback[:120]})
        if not graded.correct:
            point = {"concept": concept,
                     "misconception": graded.misconception or graded.feedback[:120],
                     "at": now_utc().isoformat()}
            self.confusion_points.append(point)
            node = f"confusion:{new_id('cf')}"
            self.g.add_node(node, kind="confusion",
                            label=point["misconception"][:80])
            self.g.add_edge(node, f"concept:{concept}", key="about", kind="about")

    # ------------------------------------------------------------------ #
    def snapshot(self) -> dict:
        return {
            "session_id": self.session_id,
            "learner": self.learner.name,
            "goal": self.roadmap.goal,
            "generated_at": now_utc().isoformat(),
            "current_activity": (json.loads(self.current_activity.model_dump_json())
                                 if self.current_activity else None),
            "mastery": {k: {"level": s.level.value,
                            "evidence": len(s.evidence),
                            "misconceptions": s.misconceptions}
                        for k, s in self.learner.mastery.items()},
            "confusion_points": self.confusion_points,
            "interactions": self.interactions[-50:],
            "learning_order": self.roadmap.learning_order,
        }

    def save(self, sessions_dir: Path) -> Path:
        sessions_dir.mkdir(parents=True, exist_ok=True)
        path = sessions_dir / f"{self.session_id}.json"
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self.snapshot(), indent=2, default=str))
        tmp.replace(path)
        return path
