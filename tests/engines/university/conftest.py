"""Offline fixtures — no network, no Ollama, no servers."""

from __future__ import annotations

import pytest

from entropy_os.engines.research.graphs.store import NetworkXJSONStore
from entropy_os.engines.research.graphs.vector_index import VectorIndex
from entropy_os.engines.research.llm.client import FakeLLM
from entropy_os.engines.university.goal import GoalAnalyzer
from entropy_os.engines.university.graphs.knowledge_graph import EducationKnowledgeGraph

ROADMAP_PROPOSAL = {
    "subject": "machine learning",
    "concepts": [
        {"name": "Machine Learning", "summary": "learning from data"},
        {"name": "Neural Networks", "summary": "layered function approximators"},
        {"name": "Linear Algebra", "summary": "vectors and matrices"},
        {"name": "Probability", "summary": "reasoning under uncertainty"},
        {"name": "Python", "summary": "the working language"},
        {"name": "Gradient Descent", "summary": "iterative optimization"},
    ],
    "edges": [
        {"src": "Machine Learning", "relation": "requires", "dst": "Linear Algebra"},
        {"src": "Machine Learning", "relation": "requires", "dst": "Probability"},
        {"src": "Machine Learning", "relation": "requires", "dst": "Python"},
        {"src": "Neural Networks", "relation": "requires", "dst": "Machine Learning"},
        {"src": "Neural Networks", "relation": "requires", "dst": "Gradient Descent"},
        {"src": "Gradient Descent", "relation": "requires", "dst": "Linear Algebra"},
        {"src": "Neural Networks", "relation": "applied_in", "dst": "Machine Learning"},
    ],
    "goal_concepts": ["Neural Networks"],
}


@pytest.fixture
async def roadmap():
    llm = FakeLLM({"plan": [ROADMAP_PROPOSAL]})
    return await GoalAnalyzer(llm).analyze("Teach me neural networks")


@pytest.fixture
def kg(tmp_path):
    return EducationKnowledgeGraph(
        NetworkXJSONStore(tmp_path / "kg.json"),
        VectorIndex(FakeLLM(), path=tmp_path / "q"))
