"""Teaching agents (gates + grading), adaptive policy, and the full loop."""

from __future__ import annotations

from datetime import timedelta

from research_engine.llm.client import FakeLLM

from learn_engine.adaptive import choose_method, next_activity
from learn_engine.models import (ActivityKind, EvidenceRow, Exercise,
                                 ExerciseKind, LearnerProfile, Mastery,
                                 now_utc)
from learn_engine.teaching import (AssessmentAgent, PracticeAgent,
                                   concept_map_mermaid, run_python_sandboxed)


class TestVisualizationAgent:
    async def test_mermaid_from_graph(self, roadmap):
        mm = concept_map_mermaid(roadmap, "Neural Networks")
        assert mm.startswith("flowchart TD")
        assert 'Neural Networks' in mm
        assert "|requires|" in mm


class TestPracticeGates:
    async def test_code_exercise_verified_by_execution(self):
        proposal = {"exercises": [{
            "kind": "code", "prompt": "print the sum of 2 and 3",
            "options": [], "answer": "5",
            "starter_code": "# TODO", "reference_solution": "print(2 + 3)",
            "rubric": ""}]}
        agent = PracticeAgent(FakeLLM({"extract": [proposal]}))
        [ex] = await agent.generate("Addition", [])
        assert ex.verified and ex.answer == "5"

    async def test_wrong_claimed_output_trusts_execution(self):
        proposal = {"exercises": [{
            "kind": "code", "prompt": "p", "options": [],
            "answer": "999",                       # LLM's claim is wrong
            "starter_code": "", "reference_solution": "print(6 * 7)",
            "rubric": ""}]}
        agent = PracticeAgent(FakeLLM({"extract": [proposal]}))
        [ex] = await agent.generate("X", [])
        assert ex.answer == "42"                   # execution wins

    async def test_broken_reference_rejected(self):
        proposal = {"exercises": [
            {"kind": "code", "prompt": "p", "options": [], "answer": "1",
             "starter_code": "", "reference_solution": "print(undefined_var)",
             "rubric": ""},
            {"kind": "mcq", "prompt": "q", "options": ["a", "b", "c", "d"],
             "answer": "B", "starter_code": "", "reference_solution": "",
             "rubric": ""}]}
        agent = PracticeAgent(FakeLLM({"extract": [proposal]}))
        out = await agent.generate("X", [])
        assert len(out) == 1 and out[0].kind == ExerciseKind.MCQ
        assert agent.rejected == 1

    async def test_malformed_mcq_and_numeric_rejected(self):
        proposal = {"exercises": [
            {"kind": "mcq", "prompt": "q", "options": ["only", "three", "opts"],
             "answer": "A", "starter_code": "", "reference_solution": "", "rubric": ""},
            {"kind": "numeric", "prompt": "q", "options": [],
             "answer": "not-a-number", "starter_code": "",
             "reference_solution": "", "rubric": ""},
            {"kind": "free_text", "prompt": "q", "options": [], "answer": "",
             "starter_code": "", "reference_solution": "", "rubric": "short"}]}
        agent = PracticeAgent(FakeLLM({"extract": [proposal]}))
        out = await agent.generate("X", [])
        assert out == [] and agent.rejected == 3

    async def test_llm_down_yields_fallback_item(self):
        agent = PracticeAgent(FakeLLM(up=False))
        out = await agent.generate("Topic", [])
        assert len(out) == 1 and out[0].verified

    async def test_sandbox_timeout(self):
        ok, out = await run_python_sandboxed("while True: pass", timeout_s=1)
        assert not ok and "timed out" in out


class TestGrading:
    async def test_deterministic_kinds(self):
        grader = AssessmentAgent(FakeLLM())
        mcq = Exercise(concept_name="X", kind=ExerciseKind.MCQ, prompt="p",
                       options=["a", "b", "c", "d"], answer="C")
        assert (await grader.grade(mcq, "c")).correct
        assert not (await grader.grade(mcq, "A")).correct
        num = Exercise(concept_name="X", kind=ExerciseKind.NUMERIC,
                       prompt="p", answer="3.5")
        assert (await grader.grade(num, "3.50")).correct
        assert not (await grader.grade(num, "3")).correct
        code = Exercise(concept_name="X", kind=ExerciseKind.CODE, prompt="p",
                        answer="42")
        assert (await grader.grade(code, "print(42)")).correct
        assert not (await grader.grade(code, "print(41)")).correct

    async def test_free_text_judge_half_weight(self):
        llm = FakeLLM({"judge": [{"correct": True, "feedback": "solid",
                                  "misconception": ""}]})
        ex = Exercise(concept_name="X", kind=ExerciseKind.FREE_TEXT,
                      prompt="p", rubric="- names the mechanism")
        graded = await AssessmentAgent(llm).grade(ex, "an answer")
        assert graded.correct and graded.weight == 0.5

    async def test_judge_down_records_ungraded(self):
        ex = Exercise(concept_name="X", kind=ExerciseKind.FREE_TEXT,
                      prompt="p", rubric="- r")
        graded = await AssessmentAgent(FakeLLM(up=False)).grade(ex, "answer")
        assert graded.weight == 0.0 and not graded.correct


class TestAdaptivePolicy:
    async def _profile(self, roadmap) -> LearnerProfile:
        return LearnerProfile(goals=[roadmap.goal])

    async def test_first_pick_is_deepest_prerequisite(self, roadmap, kg):
        await kg.absorb_roadmap(roadmap)
        profile = await self._profile(roadmap)
        act = next_activity(profile, roadmap, kg)
        assert act.kind == ActivityKind.LESSON
        assert act.concept_name == roadmap.learning_order[0]
        assert "prerequisite order" in act.reason

    async def test_overdue_review_beats_everything(self, roadmap, kg):
        await kg.absorb_roadmap(roadmap)
        profile = await self._profile(roadmap)
        s = profile.state("Python")
        s.level = Mastery.PRACTICING
        s.last_activity = now_utc() - timedelta(days=10)
        act = next_activity(profile, roadmap, kg)
        assert act.kind == ActivityKind.REVIEW and act.concept_name == "Python"

    async def test_misconception_triggers_repair(self, roadmap, kg):
        await kg.absorb_roadmap(roadmap)
        profile = await self._profile(roadmap)
        s = profile.state("Gradient Descent")
        s.level = Mastery.INTRODUCED
        s.last_activity = now_utc()
        s.misconceptions.append("thinks the gradient is a scalar")
        act = next_activity(profile, roadmap, kg)
        assert act.kind == ActivityKind.LESSON
        assert act.concept_name == "Gradient Descent"
        assert "misconception" in act.reason
        assert choose_method(profile, kg, "Gradient Descent",
                             repairing=True) == "socratic"

    async def test_mastered_concepts_are_skipped(self, roadmap, kg):
        await kg.absorb_roadmap(roadmap)
        profile = await self._profile(roadmap)
        for name in roadmap.learning_order[:-1]:
            s = profile.state(name)
            s.level = Mastery.MASTERED
            s.last_activity = now_utc()
        act = next_activity(profile, roadmap, kg)
        assert act.concept_name == roadmap.learning_order[-1]

    async def test_done_when_everything_mastered(self, roadmap, kg):
        await kg.absorb_roadmap(roadmap)
        profile = await self._profile(roadmap)
        for name in roadmap.learning_order:
            s = profile.state(name)
            s.level = Mastery.MASTERED
            s.last_activity = now_utc()
        assert next_activity(profile, roadmap, kg) is None

    async def test_cross_disciplinary_decoration(self, roadmap, kg):
        await kg.absorb_roadmap(roadmap)
        profile = await self._profile(roadmap)
        for name in roadmap.learning_order[:-1]:
            s = profile.state(name)
            s.level = Mastery.MASTERED
            s.last_activity = now_utc()
        act = next_activity(profile, roadmap, kg)
        assert "bridge" in act.reason  # path from a mastered concept shown
