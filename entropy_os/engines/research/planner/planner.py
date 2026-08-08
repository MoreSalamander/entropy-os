"""Research Intelligence Layer.

Natural-language request → ResearchPlan: domain, key entities, questions,
unknowns, conflicting viewpoints, knowledge gaps, and a roster of
specialized research agents mapped onto the live source fleet.

Deterministic-scaffold split:
  * The LLM PROPOSES the analysis (domain, entities, questions, query
    reformulations) through a schema-constrained call.
  * Deterministic code DECIDES the roster: the ten agent archetypes and
    their source mappings are fixed here in AGENT_ARCHETYPES, every archetype
    is always staffed, and each agent's sources are filtered to adapters
    that are actually live. If the LLM is down, a deterministic fallback
    plan still produces a working (if less tailored) research run.
  * The Knowledge Graph is consulted BEFORE searching: entities already
    known become `known_context` (avoid relearning), unknown-but-referenced
    ones become explicit `knowledge_gaps`.
"""

from __future__ import annotations

from ..llm.client import LLMClient, LLMUnavailable
from ..models import AgentSpec, ResearchPlan

# The spec's ten-agent roster, each mapped to real adapters in priority order.
# Filtered at plan time to sources that are actually live/degraded.
AGENT_ARCHETYPES: list[dict] = [
    {"name": "Academic Research Agent",
     "focus": "peer-reviewed papers, preprints, citations, methods",
     "sources": ["openalex", "arxiv", "semantic_scholar", "pubmed", "crossref", "ieee"]},
    {"name": "Industry Research Agent",
     "focus": "companies, products, funding, strategy",
     "sources": ["gdelt_news", "brave_search", "serper", "wikipedia", "hackernews"]},
    {"name": "Patent Agent",
     "focus": "filed and granted patents, inventors, assignees",
     "sources": ["patentsview", "wipo"]},
    {"name": "Open Source Agent",
     "focus": "repositories, implementations, tooling maturity",
     "sources": ["github", "gitlab", "huggingface"]},
    {"name": "Market Agent",
     "focus": "market size, adoption, competition, demand signals",
     "sources": ["gdelt_news", "newsapi", "brave_search", "wikipedia"]},
    {"name": "News Agent",
     "focus": "recent events and announcements",
     "sources": ["gdelt_news", "newsapi", "hackernews"]},
    {"name": "Expert Opinion Agent",
     "focus": "practitioner and expert commentary, debates",
     "sources": ["hackernews", "reddit", "stackexchange"]},
    {"name": "Historical Context Agent",
     "focus": "origins, prior generations, how the field got here",
     "sources": ["wikipedia", "openalex", "crossref"]},
    {"name": "Technical Documentation Agent",
     "focus": "specifications, docs, standards, benchmarks",
     "sources": ["github", "huggingface", "stackexchange", "wikipedia"]},
    {"name": "Regulatory Agent",
     "focus": "government datasets, rules, public-sector activity",
     "sources": ["datagov", "gdelt_news", "wikipedia"]},
]

_PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "domain": {"type": "string"},
        "key_entities": {"type": "array", "items": {"type": "string"}},
        "research_questions": {"type": "array", "items": {"type": "string"}},
        "unknowns": {"type": "array", "items": {"type": "string"}},
        "conflicting_viewpoints": {"type": "array", "items": {"type": "string"}},
        "query_variants": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["domain", "key_entities", "research_questions",
                 "unknowns", "conflicting_viewpoints", "query_variants"],
}

_PLAN_SYSTEM = """You are the planning module of a research engine.
Given a research topic, produce a rigorous research framing as JSON:
- domain: the primary field this belongs to
- key_entities: 5-12 concrete entities (technologies, companies, people, papers, concepts) central to the topic
- research_questions: 4-8 specific questions a thorough investigation must answer
- unknowns: 3-6 genuinely open or uncertain variables
- conflicting_viewpoints: 2-5 real disagreements or debates in this area
- query_variants: 3-6 distinct search-query phrasings of the topic (different vocabulary, not rewordings)
Be concrete. No filler."""


class ResearchPlanner:
    def __init__(self, llm: LLMClient, query_variants: int = 2):
        self.llm = llm
        self.query_variants = query_variants

    async def plan(self, topic: str, live_sources: list[str],
                   kg_known: list[str] | None = None) -> ResearchPlan:
        """Build the plan. kg_known = entity names the Knowledge Graph already
        holds for this topic (injected by the orchestrator's KG pre-query)."""
        kg_known = kg_known or []
        proposal: dict = {}
        try:
            user = f"Research topic: {topic}"
            if kg_known:
                user += ("\n\nAlready known from prior research (do NOT re-plan these "
                         f"as gaps; build on them): {', '.join(kg_known[:30])}")
            proposal = await self.llm.chat_json("plan", _PLAN_SYSTEM, user, _PLAN_SCHEMA)
        except LLMUnavailable:
            proposal = {}  # deterministic fallback below still yields a working plan

        # ---- deterministic validation & assembly ------------------------
        def _strs(key: str, fallback: list[str]) -> list[str]:
            vals = proposal.get(key)
            if not isinstance(vals, list):
                return fallback
            clean = [v.strip() for v in vals if isinstance(v, str) and v.strip()]
            return clean or fallback

        variants = _strs("query_variants", [topic])[: self.query_variants + 1]
        if topic not in variants:
            variants.insert(0, topic)

        known_norm = {k.casefold() for k in kg_known}
        key_entities = _strs("key_entities", [])
        # Entities the plan names but the KG lacks are the knowledge gaps.
        gaps = [e for e in key_entities if e.casefold() not in known_norm]

        # Roster: every archetype staffed, sources filtered to live adapters.
        live = set(live_sources)
        agents: list[AgentSpec] = []
        for arch in AGENT_ARCHETYPES:
            usable = [s for s in arch["sources"] if s in live]
            if not usable:
                continue  # e.g. Patent Agent with no patent key: reported via source table
            agents.append(AgentSpec(
                name=arch["name"], focus=arch["focus"], sources=usable,
                queries=variants,
                extraction_emphasis=arch["focus"],
            ))

        return ResearchPlan(
            topic=topic,
            domain=str(proposal.get("domain") or "general"),
            key_entities=key_entities,
            research_questions=_strs("research_questions",
                                     [f"What is the current state of {topic}?",
                                      f"What are the open problems in {topic}?"]),
            unknowns=_strs("unknowns", [f"Trajectory of {topic} over the next 3 years"]),
            conflicting_viewpoints=_strs("conflicting_viewpoints", []),
            knowledge_gaps=gaps,
            known_context=kg_known,
            agents=agents,
        )
