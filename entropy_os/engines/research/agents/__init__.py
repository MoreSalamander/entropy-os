from .base import GraphAgent
from .insight import AnalystAgent, DiscoveryAgent, QuestionAgent, TrendAgent
from .verify import ContradictionAgent, VerificationAgent

ALL_AGENTS = [VerificationAgent, ContradictionAgent, AnalystAgent,
              DiscoveryAgent, TrendAgent, QuestionAgent]

__all__ = ["GraphAgent", "VerificationAgent", "ContradictionAgent",
           "AnalystAgent", "DiscoveryAgent", "TrendAgent", "QuestionAgent",
           "ALL_AGENTS"]
