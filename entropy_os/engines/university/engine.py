"""Engine assembly — the personal-university loop.

    start(goal)            roadmap + research + KG absorption
    next()                 adaptive policy chooses the activity, the
                           teaching org builds it (lesson/practice bundle)
    submit(answers)        grading → evidence → mastery → misconception log
                           → method stats (learner + shared KG) → context
                           graph update

Every state change is persisted (learner profile, session graph, lesson
bundles) and the session is emitted to DataHub with agent lineage.
"""

from __future__ import annotations

from pathlib import Path

from entropy_os.engines.research.config import LLMConfig
from entropy_os.engines.research.graphs.store import NetworkXJSONStore
from entropy_os.engines.research.graphs.vector_index import VectorIndex
from entropy_os.engines.research.llm.client import LLMClient, OllamaClient

from .adaptive import choose_method, next_activity
from .goal import GoalAnalyzer
from .graphs.context_graph import StudentContextGraph
from .graphs.datahub_bridge import LearnDataHubBridge
from .graphs.knowledge_graph import EducationKnowledgeGraph
from .learner import (apply_evidence, mark_introduced, record_method_outcome,
                      save_profile)
from .models import (Activity, ActivityKind, EvidenceRow, Exercise,
                     GradedAnswer, LearnerProfile, Mastery, Roadmap, new_id)
from .research import RESEARCH_AGENTS, EducationalResearch
from .teaching import AssessmentAgent, LessonBuilder, PracticeAgent
from ...paths import engine_storage

# This engine's own accumulated knowledge and artifacts, addressed by its
# contract member key rather than by the repository it used to live in.
STORAGE = engine_storage("university")
PROJECT_ROOT = STORAGE

RESEARCH_CONCEPT_CAP = 6   # research the goal tier + first prerequisites;
#                            deeper tiers get researched when reached


class LearnEngine:
    def __init__(self, llm: LLMClient | None = None,
                 storage_dir: Path | None = None,
                 datahub_gms: str = "http://localhost:8080"):
        self.llm = llm or OllamaClient(LLMConfig(timeout_s=300))
        storage = storage_dir or STORAGE
        storage.mkdir(parents=True, exist_ok=True)
        self.storage = storage
        vectors = VectorIndex(self.llm, path=storage / "qdrant")
        self.kg = EducationKnowledgeGraph(
            NetworkXJSONStore(storage / "education_kg.json"), vectors)
        self.datahub = LearnDataHubBridge(gms_url=datahub_gms)
        self._probed = False
        # per-session working state
        self.session_id: str = ""
        self.profile: LearnerProfile | None = None
        self.roadmap: Roadmap | None = None
        self.cg: StudentContextGraph | None = None
        self.activities_done = 0
        self.graded_items = 0
        self.correct_items = 0

    # ------------------------------------------------------------------ #
    async def start(self, goal: str, learner_name: str = "learner",
                    log=print) -> Roadmap:
        if not self._probed:
            await self.datahub.probe()
            self._probed = True
        self.session_id = new_id("study")
        self.profile = LearnerProfile(name=learner_name, goals=[goal])

        roadmap = await GoalAnalyzer(self.llm).analyze(goal)
        self.roadmap = roadmap
        log(f"[goal] {roadmap.subject}: {len(roadmap.concepts)} concepts, "
            f"{len(roadmap.edges)} relations; order: "
            f"{' → '.join(roadmap.learning_order[:6])}"
            + (" …" if len(roadmap.learning_order) > 6 else ""))
        for note in roadmap.validation_notes[:4]:
            log(f"  [gate] {note}")

        await self.kg.absorb_roadmap(roadmap)
        research = EducationalResearch()
        try:
            from .research import concepts_to_research
            resources, stats = await research.research_concepts(
                concepts_to_research(roadmap.learning_order,
                                     RESEARCH_CONCEPT_CAP))
        finally:
            await research.aclose()
        self.kg.absorb_resources(resources)
        log(f"[research] {stats['resources_total']} resources "
            f"({stats['concepts_researched']} concepts): "
            + ", ".join(f"{k.split()[0]}={v}"
                        for k, v in stats["by_agent"].items()))

        self.cg = StudentContextGraph(self.session_id, self.profile, roadmap)
        return roadmap

    # ------------------------------------------------------------------ #
    async def next(self, log=print) -> Activity | None:
        assert self.profile and self.roadmap and self.cg, "call start() first"
        activity = next_activity(self.profile, self.roadmap, self.kg)
        if activity is None:
            log("[adaptive] roadmap fully mastered — nothing left to teach")
            return None
        log(f"[adaptive] {activity.kind.value} on “{activity.concept_name}” — "
            f"{activity.reason}")

        concept = activity.concept_name
        state = self.profile.state(concept)
        repairing = bool(state.misconceptions) and activity.kind == ActivityKind.LESSON
        misconceptions = (state.misconceptions
                          + self.kg.misconceptions_for(concept))
        practice = PracticeAgent(self.llm)
        exercises = await practice.generate(concept, misconceptions,
                                            n=3 if activity.kind ==
                                            ActivityKind.REVIEW else 4)
        if practice.rejected:
            log(f"  [gate] {practice.rejected} exercise(s) rejected "
                "(unverifiable or malformed)")

        if activity.kind in (ActivityKind.LESSON, ActivityKind.REVIEW):
            method = choose_method(self.profile, self.kg, concept, repairing)
            lesson = await LessonBuilder(self.llm).build(
                concept, self.roadmap, method,
                [rd for rd in self._resources_as_models(concept)],
                misconceptions, exercises)
            activity.lesson = lesson
            mark_introduced(state)
            bundle_dir = self.storage / "lessons" / self.session_id
            bundle_dir.mkdir(parents=True, exist_ok=True)
            base = bundle_dir / f"{lesson.id}"
            base.with_suffix(".md").write_text(LessonBuilder.to_markdown(lesson))
            base.with_suffix(".html").write_text(LessonBuilder.to_html(lesson))
            log(f"  [lesson] method={method}, {len(lesson.resources)} resources, "
                f"{len(exercises)} exercises → {base}.md/.html")
        activity.exercises = exercises
        self.cg.begin_activity(activity)
        self.activities_done += 1
        return activity

    def _resources_as_models(self, concept: str):
        from .models import LearningResource
        return [LearningResource(concept_name=concept, kind=r["kind"],
                                 title=r["title"], url=r["url"],
                                 agent=r["agent"])
                for r in self.kg.resources_for(concept)]

    # ------------------------------------------------------------------ #
    async def submit(self, activity: Activity,
                     answers: dict[str, str], log=print) -> list[GradedAnswer]:
        assert self.profile and self.cg
        grader = AssessmentAgent(self.llm)
        method = activity.lesson.method if activity.lesson else "practice"
        graded: list[GradedAnswer] = []
        state = self.profile.state(activity.concept_name)
        for ex in activity.exercises:
            if ex.id not in answers:
                continue
            result = await grader.grade(ex, answers[ex.id])
            graded.append(result)
            self.graded_items += 1
            self.correct_items += int(result.correct)
            if result.weight > 0:
                level = apply_evidence(state, EvidenceRow(
                    activity_id=activity.id, item_kind=ex.kind.value,
                    correct=result.correct, weight=result.weight,
                    method=method, detail=result.feedback[:120]))
                record_method_outcome(self.profile, method, result.correct)
                self.kg.record_explanation_outcome(activity.concept_name,
                                                   method, result.correct)
                log(f"  [{'✓' if result.correct else '✗'}] {ex.kind.value}: "
                    f"{result.feedback[:70]} → {activity.concept_name} is "
                    f"{level.value}")
            self.cg.record_answer(activity.concept_name, result)
            if result.misconception:
                state.misconceptions.append(result.misconception)
                self.kg.record_misconception(activity.concept_name,
                                             result.misconception)
        # a correct answer after a repair lesson clears the misconception log
        if state.misconceptions and graded and all(g.correct for g in graded):
            log(f"  [repair] misconceptions cleared on {activity.concept_name}")
            state.misconceptions.clear()
        save_profile(self.profile, self.storage / "learners")
        self.cg.save(self.storage / "sessions")
        return graded

    # ------------------------------------------------------------------ #
    async def finish(self, log=print) -> str:
        assert self.profile and self.roadmap
        status = await self.datahub.emit_session(
            self.session_id, self.profile, self.roadmap,
            self.activities_done, self.graded_items, self.correct_items,
            RESEARCH_AGENTS)
        log(f"[memory] learner profile + session saved; datahub: {status}")
        return status

    async def aclose(self) -> None:
        self.kg.store.close()
        self.kg.vectors.close()
        if isinstance(self.llm, OllamaClient):
            await self.llm.aclose()


def mastery_report(profile: LearnerProfile, roadmap: Roadmap) -> str:
    lines = [f"# Mastery: {roadmap.goal}", ""]
    icons = {Mastery.UNKNOWN: "·", Mastery.INTRODUCED: "○",
             Mastery.PRACTICING: "◐", Mastery.MASTERED: "●"}
    for name in roadmap.learning_order:
        s = profile.state(name)
        extra = (f"  ⚠ {s.misconceptions[-1][:50]}" if s.misconceptions else "")
        lines.append(f"{icons[s.level]} {name:<40} {s.level.value:<12}"
                     f"({len(s.evidence)} evidence){extra}")
    return "\n".join(lines)
