from .base import GraphAgent
from .verify import ContradictionAgent, VerificationAgent
from .insight import AnalystAgent, DiscoveryAgent, QuestionAgent, TrendAgent

ALL_AGENTS = [VerificationAgent, ContradictionAgent, AnalystAgent,
              DiscoveryAgent, TrendAgent, QuestionAgent]

__all__ = ["GraphAgent", "VerificationAgent", "ContradictionAgent",
           "AnalystAgent", "DiscoveryAgent", "TrendAgent", "QuestionAgent",
           "ALL_AGENTS"]
