"""Goal analysis, learner-model rubric, knowledge-graph reasoning."""

from __future__ import annotations

from datetime import timedelta

from research_engine.llm.client import FakeLLM

from learn_engine.goal import GoalAnalyzer
from learn_engine.learner import (apply_evidence, mark_introduced,
                                  preferred_method, record_method_outcome)
from learn_engine.models import (EvidenceRow, LearnerProfile, Mastery,
                                 MasteryState, now_utc)

from conftest import ROADMAP_PROPOSAL


class TestGoalAnalysis:
    async def test_topological_order_respects_requires(self, roadmap):
        order = roadmap.learning_order
        pos = {name: i for i, name in enumerate(order)}
        # every prerequisite strictly before its dependent
        for s, rel, d in roadmap.edges:
            if rel == "requires":
                assert pos[d] < pos[s], f"{d} must precede {s}"
        assert order[-1] == "Neural Networks"  # goal comes last

    async def test_goal_depth_zero_prereqs_deeper(self, roadmap):
        depth = {c.name: c.depth for c in roadmap.concepts}
        assert depth["Neural Networks"] == 0
        assert depth["Linear Algebra"] >= 2  # two hops below the goal

    async def test_cycle_broken_with_note(self):
        proposal = {
            "subject": "s",
            "concepts": [{"name": "A", "summary": "a"},
                         {"name": "B", "summary": "b"}],
            "edges": [{"src": "A", "relation": "requires", "dst": "B"},
                      {"src": "B", "relation": "requires", "dst": "A"}],
            "goal_concepts": ["A"],
        }
        roadmap = await GoalAnalyzer(FakeLLM({"plan": [proposal]})).analyze("x")
        assert any("circular" in n for n in roadmap.validation_notes)
        requires = [(s, d) for s, r, d in roadmap.edges if r == "requires"]
        assert len(requires) == 1  # one edge survived
        assert len(roadmap.learning_order) == 2

    async def test_llm_down_minimal_roadmap(self):
        roadmap = await GoalAnalyzer(FakeLLM(up=False)).analyze("learn sailing")
        assert len(roadmap.concepts) == 1
        assert roadmap.learning_order

    async def test_duplicate_concepts_merged(self):
        proposal = dict(ROADMAP_PROPOSAL)
        proposal = {**proposal, "concepts": proposal["concepts"]
                    + [{"name": "linear-algebra!", "summary": "dup"}]}
        roadmap = await GoalAnalyzer(FakeLLM({"plan": [proposal]})).analyze("x")
        names = [c.name.casefold().replace("-", " ") for c in roadmap.concepts]
        assert names.count("linear algebra") == 1


def _row(kind: str, correct: bool, weight: float = 1.0) -> EvidenceRow:
    return EvidenceRow(item_kind=kind, correct=correct, weight=weight)


class TestMasteryRubric:
    def test_lesson_introduces(self):
        s = MasteryState(concept_name="X")
        mark_introduced(s)
        assert s.level == Mastery.INTRODUCED

    def test_first_correct_promotes_to_practicing(self):
        s = MasteryState(concept_name="X", level=Mastery.INTRODUCED)
        assert apply_evidence(s, _row("mcq", True)) == Mastery.PRACTICING

    def test_mastery_needs_streak_across_kinds(self):
        s = MasteryState(concept_name="X", level=Mastery.PRACTICING)
        # 3 correct but all one kind → NOT mastered (breadth rule)
        for _ in range(3):
            apply_evidence(s, _row("mcq", True))
        assert s.level == Mastery.PRACTICING
        # a different kind completes the rubric
        apply_evidence(s, _row("code", True))
        assert s.level == Mastery.MASTERED

    def test_two_misses_demote(self):
        s = MasteryState(concept_name="X", level=Mastery.MASTERED)
        apply_evidence(s, _row("mcq", False))
        assert s.level == Mastery.MASTERED  # one miss forgiven
        apply_evidence(s, _row("numeric", False))
        assert s.level == Mastery.PRACTICING
        # never below INTRODUCED
        apply_evidence(s, _row("mcq", False))
        apply_evidence(s, _row("mcq", False))
        assert s.level in (Mastery.INTRODUCED, Mastery.PRACTICING)
        for _ in range(4):
            apply_evidence(s, _row("mcq", False))
        assert s.level == Mastery.INTRODUCED

    def test_half_weight_judged_items_cannot_complete_streak_alone(self):
        s = MasteryState(concept_name="X", level=Mastery.PRACTICING)
        # three correct free-text answers (0.5 each) span only one kind AND
        # miss the weight floor → no mastery
        for _ in range(3):
            apply_evidence(s, _row("free_text", True, weight=0.5))
        assert s.level == Mastery.PRACTICING

    def test_review_schedule(self):
        s = MasteryState(concept_name="X", level=Mastery.PRACTICING)
        s.last_activity = now_utc() - timedelta(days=4)
        assert s.review_due is not None and s.review_due <= now_utc()
        s.level = Mastery.MASTERED
        assert s.review_due > now_utc()  # 21-day interval not yet elapsed

    def test_method_stats_and_preference(self):
        p = LearnerProfile()
        for _ in range(3):
            record_method_outcome(p, "socratic", True)
        record_method_outcome(p, "teacher", False)
        record_method_outcome(p, "teacher", False)
        assert preferred_method(p) == "socratic"


class TestKnowledgeGraphReasoning:
    async def test_missing_prerequisites_deepest_first(self, kg, roadmap):
        await kg.absorb_roadmap(roadmap)
        gaps = kg.missing_prerequisites("Neural Networks", mastered=["Python"])
        assert "Python" not in gaps
        assert "Linear Algebra" in gaps and "Machine Learning" in gaps
        assert gaps.index("Linear Algebra") < gaps.index("Machine Learning")

    async def test_cross_disciplinary_paths(self, kg, roadmap):
        await kg.absorb_roadmap(roadmap)
        paths = kg.cross_disciplinary(["Linear Algebra"], "Neural Networks")
        assert paths and paths[0][0] == "Linear Algebra"
        assert paths[0][-1] == "Neural Networks"

    async def test_explanation_memory_and_misconceptions(self, kg, roadmap):
        await kg.absorb_roadmap(roadmap)
        for _ in range(2):
            kg.record_explanation_outcome("Gradient Descent", "socratic", True)
        kg.record_explanation_outcome("Gradient Descent", "teacher", False)
        kg.record_explanation_outcome("Gradient Descent", "teacher", False)
        assert kg.best_method_for("Gradient Descent") == "socratic"
        kg.record_misconception("Gradient Descent",
                                "confuses learning rate with gradient")
        assert any("learning rate" in m
                   for m in kg.misconceptions_for("Gradient Descent"))


class TestResearchSlicing:
    def test_research_covers_first_taught_concepts(self):
        # regression: the live run researched the goal tier and taught the
        # deepest prerequisite (Calculus, position 1) with zero resources
        from learn_engine.research import concepts_to_research
        order = ["Calculus", "Linear Algebra", "Probability", "Python",
                 "Gradient Descent", "ML", "NN", "Transformers"]
        assert concepts_to_research(order, 6) == order[:6]
        assert concepts_to_research(order, 6)[0] == "Calculus"
