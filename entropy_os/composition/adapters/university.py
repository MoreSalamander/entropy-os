"""University engine adapter — wraps entropy_os.engines.university.LearnEngine.

LearnEngine is deliberately session-stateful (start → next → submit → finish
is one continuous teaching loop), so this adapter is the reason leaf adapters
are long-lived processes: it holds live LearnEngine sessions between contract
calls, keyed by session_id, and holds prepared activities so a later assess
call can grade against the exact exercises that were issued.
"""

from __future__ import annotations

import os

from ..contract import ArtifactRef, CapabilitySpec, ExecuteRequest, FieldSpec
from ..llm import build_llm
from .base import Emit, LeafAdapter


class UniversityAdapter(LeafAdapter):
    name = "learn-engine"
    description = ("Personal university: goal → prerequisite-DAG roadmap → "
                   "researched resources → adaptive lesson/practice loop → "
                   "evidence-based mastery with misconception repair.")
    datahub_platform = "learn-engine"
    engine_module = "entropy_os.engines.university.engine"
    events_emitted = ["CurriculumCreated", "LessonBuilt", "RoadmapMastered",
                      "MasteryEvidenceRecorded", "MisconceptionDetected",
                      "LearningSessionCompleted"]

    def __init__(self):
        super().__init__()
        self._sessions: dict[str, object] = {}      # session_id → LearnEngine
        self._activities: dict[str, object] = {}    # activity_id → Activity

    def _new_engine(self):
        from entropy_os.engines.university.engine import LearnEngine
        return LearnEngine(
            llm=build_llm(),          # None on local → the engine's own client
            datahub_gms=os.environ.get("DATAHUB_GMS",
                                       "http://localhost:8080"))

    def _session(self, session_id: str):
        eng = self._sessions.get(session_id)
        if eng is None:
            raise ValueError(f"unknown learning session {session_id!r}; "
                             "run university.design_curriculum first")
        return eng

    def capabilities(self) -> list[CapabilitySpec]:
        return [
            CapabilitySpec(
                name="university.design_curriculum",
                summary="Analyze a learning goal into a prerequisite-ordered "
                        "concept roadmap and research resources for it.",
                long_running=True,
                inputs={"goal": FieldSpec(type="string", required=True),
                        "learner_name": FieldSpec(type="string")},
                outputs={"session_id": FieldSpec(),
                         "subject": FieldSpec(),
                         "learning_order": FieldSpec(type="array")},
                tags=["education", "curriculum"]),
            CapabilitySpec(
                name="university.next_activity",
                summary="Let the adaptive policy choose and build the next "
                        "lesson/practice/review activity.",
                long_running=True,
                inputs={"session_id": FieldSpec(type="string", required=True)},
                outputs={"activity_id": FieldSpec(),
                         "concept": FieldSpec(),
                         "exercises": FieldSpec(type="array")},
                tags=["education", "teaching"]),
            CapabilitySpec(
                name="university.assess",
                summary="Grade submitted answers; update mastery evidence "
                        "and the misconception log.",
                inputs={"session_id": FieldSpec(type="string", required=True),
                        "activity_id": FieldSpec(type="string", required=True),
                        "answers": FieldSpec(type="object", required=True,
                                             description="exercise_id → answer")},
                outputs={"graded": FieldSpec(type="array"),
                         "mastery_level": FieldSpec()},
                tags=["education", "assessment"]),
            CapabilitySpec(
                name="university.finish_session",
                summary="Close the session: emit DataHub provenance and "
                        "return the mastery report.",
                inputs={"session_id": FieldSpec(type="string", required=True)},
                outputs={"mastery_report_md": FieldSpec(),
                         "datahub_status": FieldSpec()},
                tags=["education"]),
        ]

    async def _run(self, req: ExecuteRequest, emit: Emit):
        cap = req.capability
        notes: list[str] = []

        def log(line) -> None:
            # learn-engine narrates richly; keep it as provenance notes and
            # let the adapter emit the *meaningful* facts explicitly below.
            notes.append(str(line))

        if cap == "university.design_curriculum":
            goal = str(req.inputs.get("goal", "")).strip()
            if not goal:
                raise ValueError("design_curriculum requires inputs.goal")
            eng = self._new_engine()
            roadmap = await eng.start(
                goal, learner_name=req.inputs.get("learner_name", "learner"),
                log=log)
            self._sessions[eng.session_id] = eng
            urn = self.dataset_urn(f"session.{eng.session_id}")
            emit("CurriculumCreated", subject=urn, goal=goal,
                 session_id=eng.session_id, subject_area=roadmap.subject,
                 concepts=len(roadmap.concepts),
                 learning_order=roadmap.learning_order)
            outputs = {"session_id": eng.session_id,
                       "goal": goal,
                       "subject": roadmap.subject,
                       "concepts": len(roadmap.concepts),
                       "learning_order": roadmap.learning_order,
                       "validation_notes": roadmap.validation_notes}
            return outputs, [], [urn], notes

        if cap == "university.next_activity":
            session_id = str(req.inputs.get("session_id", ""))
            eng = self._session(session_id)
            activity = await eng.next(log=log)
            if activity is None:
                emit("RoadmapMastered", subject=session_id)
                return {"done": True, "session_id": session_id}, [], [], notes
            self._activities[activity.id] = activity
            artifacts = []
            if activity.lesson is not None:
                base = (eng.storage / "lessons" / session_id
                        / activity.lesson.id)
                artifacts.append(ArtifactRef(
                    kind="lesson", path=f"{base}.md",
                    description=f"lesson: {activity.concept_name} "
                                f"({activity.lesson.method})"))
                emit("LessonBuilt", subject=activity.concept_name,
                     session_id=session_id, method=activity.lesson.method,
                     exercises=len(activity.exercises))
            outputs = {
                "session_id": session_id,
                "activity_id": activity.id,
                "kind": activity.kind.value,
                "concept": activity.concept_name,
                "reason": activity.reason,
                # Answers/rubrics stay engine-side — the contract exposes the
                # student surface, not the answer key.
                "exercises": [{"id": ex.id, "kind": ex.kind.value,
                               "prompt": ex.prompt, "options": ex.options}
                              for ex in activity.exercises],
            }
            return outputs, artifacts, [], notes

        if cap == "university.assess":
            session_id = str(req.inputs.get("session_id", ""))
            eng = self._session(session_id)
            activity = self._activities.get(str(req.inputs.get("activity_id")))
            if activity is None:
                raise ValueError("unknown activity_id; call "
                                 "university.next_activity first")
            answers = dict(req.inputs.get("answers") or {})
            graded = await eng.submit(activity, answers, log=log)
            level = eng.profile.state(activity.concept_name).level.value
            emit("MasteryEvidenceRecorded", subject=activity.concept_name,
                 session_id=session_id,
                 correct=sum(1 for g in graded if g.correct),
                 total=len(graded), mastery_level=level)
            for g in graded:
                if g.misconception:
                    emit("MisconceptionDetected",
                         subject=activity.concept_name,
                         misconception=g.misconception)
            outputs = {
                "session_id": session_id,
                "graded": [{"exercise_id": g.exercise_id,
                            "correct": g.correct,
                            "feedback": g.feedback,
                            "misconception": g.misconception}
                           for g in graded],
                "mastery_level": level,
            }
            return outputs, [], [], notes

        if cap == "university.finish_session":
            session_id = str(req.inputs.get("session_id", ""))
            eng = self._session(session_id)
            from entropy_os.engines.university.engine import mastery_report
            status = await eng.finish(log=log)
            report_md = mastery_report(eng.profile, eng.roadmap)
            urn = self.dataset_urn(f"session.{session_id}")
            emit("LearningSessionCompleted", subject=urn,
                 session_id=session_id,
                 activities=eng.activities_done,
                 graded=eng.graded_items, correct=eng.correct_items)
            outputs = {"session_id": session_id,
                       "datahub_status": status,
                       "mastery_report_md": report_md}
            return outputs, [], [urn], notes

        raise ValueError(f"unhandled capability {cap!r}")

    async def aclose(self) -> None:
        for eng in self._sessions.values():
            await eng.aclose()
        self._sessions.clear()
        self._activities.clear()
