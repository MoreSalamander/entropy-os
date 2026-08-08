"""Graph-reasoning agent contract.

Each agent reads the session's Context Graph (and optionally the Knowledge
Graph), produces typed Findings, and follows the same law as every other
layer: deterministic candidate generation first, LLM only to confirm or to
voice — and every finding cites evidence ids that exist in the session.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..graphs.context_graph import ContextGraph
from ..graphs.knowledge_graph import KnowledgeGraph
from ..llm.client import LLMClient
from ..models import Finding


class GraphAgent(ABC):
    name: str = "agent"

    def __init__(self, llm: LLMClient):
        self.llm = llm

    @abstractmethod
    async def analyze(self, cg: ContextGraph,
                      kg: KnowledgeGraph | None = None) -> list[Finding]: ...
