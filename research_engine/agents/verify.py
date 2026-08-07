"""The gate pair: Verification Agent + Contradiction Agent.

These two decide what counts as knowledge. They are deliberately the most
deterministic agents in the system — the Verification gate uses no LLM at
all, and the Contradiction agent only asks the judge model to confirm
candidates that deterministic pairing already produced.
"""

from __future__ import annotations

from ..graphs.context_graph import ContextGraph
from ..graphs.knowledge_graph import KnowledgeGraph
from ..llm.client import LLMUnavailable
from ..models import Finding
from .base import GraphAgent

# Verification thresholds — the hard floor between context and knowledge.
MIN_RELIABILITY = 0.45      # best supporting evidence must clear this
STRONG_RELIABILITY = 0.7    # single high-trust source may verify alone
MIN_SOURCES_WEAK = 2        # weaker evidence needs independent corroboration


class VerificationAgent(GraphAgent):
    """Checks evidence quality claim by claim. Pure deterministic policy:

        verified  ⇐  best_reliability >= 0.7
                  or (distinct_sources >= 2 and best_reliability >= 0.45)

    Marks each claim in place (claim.verified) and recomputes claim
    confidence as corroboration-boosted mean reliability. The set of
    verified claim ids is what the consolidator is allowed to promote."""

    name = "Verification Agent"

    async def analyze(self, cg: ContextGraph,
                      kg: KnowledgeGraph | None = None) -> list[Finding]:
        findings: list[Finding] = []
        verified = 0
        for claim in cg.claims.values():
            if not claim.evidence:
                claim.verified = False  # unreachable by construction, enforced anyway
                continue
            best = max(ev.reliability for ev in claim.evidence)
            sources = {ev.source for ev in claim.evidence}
            mean = sum(ev.reliability for ev in claim.evidence) / len(claim.evidence)
            claim.confidence = round(
                min(0.99, mean + min(0.2, 0.05 * (len(sources) - 1))), 3)
            claim.verified = (best >= STRONG_RELIABILITY
                              or (len(sources) >= MIN_SOURCES_WEAK
                                  and best >= MIN_RELIABILITY))
            verified += int(claim.verified)
        total = len(cg.claims)
        findings.append(Finding(
            agent=self.name, kind="verification",
            text=(f"{verified}/{total} claims verified "
                  f"(floor: reliability≥{STRONG_RELIABILITY} single-source, "
                  f"or ≥{MIN_SOURCES_WEAK} independent sources at ≥{MIN_RELIABILITY})"),
            confidence=1.0))
        return findings


_CONTRA_SCHEMA = {
    "type": "object",
    "properties": {"contradicts": {"type": "boolean"},
                   "explanation": {"type": "string"}},
    "required": ["contradicts", "explanation"],
}

_CONTRA_SYSTEM = """You judge whether two claims genuinely contradict each other.
contradicts=true only if both cannot be true at once. Different aspects,
different timeframes, or complementary observations are NOT contradictions."""


class ContradictionAgent(GraphAgent):
    """Confirms or clears the Context Graph's deterministic candidate pairs.
    Confirmed disagreements become findings citing BOTH sides' evidence —
    disagreement is a research result, not a failure."""

    name = "Contradiction Agent"
    MAX_JUDGED = 12  # judge-call budget per session; candidates beyond it stay listed as unresolved

    async def analyze(self, cg: ContextGraph,
                      kg: KnowledgeGraph | None = None) -> list[Finding]:
        findings: list[Finding] = []
        for a_id, b_id in cg.contradiction_candidates[: self.MAX_JUDGED]:
            a, b = cg.claims.get(a_id), cg.claims.get(b_id)
            if not a or not b:
                continue
            try:
                verdict = await self.llm.chat_json(
                    "judge", _CONTRA_SYSTEM,
                    f"Claim A: {a.statement}\nClaim B: {b.statement}",
                    _CONTRA_SCHEMA)
            except LLMUnavailable:
                break  # no judge → candidates stay candidates; never auto-confirm
            if verdict.get("contradicts") is True:
                findings.append(Finding(
                    agent=self.name, kind="contradiction",
                    text=(f"Disagreement: \"{a.statement[:120]}\" vs "
                          f"\"{b.statement[:120]}\" — "
                          f"{str(verdict.get('explanation', ''))[:200]}"),
                    entity_ids=list(set(a.entity_ids) & set(b.entity_ids)),
                    evidence_ids=[ev.id for ev in a.evidence + b.evidence],
                    confidence=min(a.confidence, b.confidence)))
        return findings
