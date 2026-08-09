"""Phase 1 — User Intent Analysis.

Natural-language idea → ProjectIntent: industry, audience, brand position,
user goals, required pages, and the SEMANTIC TRAITS that drive Phase 2
(the spec's "search by intent, not keyword": 'medical trust', 'enterprise
credibility', 'scientific authority' — axes, not query strings).

Deterministic-scaffold split: the LLM proposes the analysis through a
schema gate; deterministic code validates page kinds against the known
enum, guarantees a landing page exists, derives a product name when the
LLM offers none, and falls back to a workable default intent if the LLM
is down.
"""

from __future__ import annotations

import re

from entropy_os.engines.research.llm.client import LLMClient, LLMUnavailable

from ..models import PageKind, ProjectIntent

_INTENT_SCHEMA = {
    "type": "object",
    "properties": {
        "industry": {"type": "string"},
        "product_name": {"type": "string"},
        "audience": {"type": "array", "items": {"type": "string"}},
        "brand_position": {"type": "array", "items": {"type": "string"}},
        "user_goals": {"type": "array", "items": {"type": "string"}},
        "required_pages": {"type": "array",
                           "items": {"type": "string",
                                     "enum": [p.value for p in PageKind]}},
        "semantic_traits": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["industry", "product_name", "audience", "brand_position",
                 "user_goals", "required_pages", "semantic_traits"],
}

_INTENT_SYSTEM = """You are the intent-analysis module of a website design engine.
From the user's request, extract as JSON:
- industry: the specific vertical (e.g. "Healthcare AI", not "technology")
- product_name: a short plausible product/company name from the request (invent a neutral one if absent)
- audience: 2-5 concrete audience groups
- brand_position: 3-5 adjectives the brand must communicate
- user_goals: 2-4 site goals (e.g. lead generation, education, credibility)
- required_pages: which of [landing, product, about, pricing, contact, docs] this site needs
- semantic_traits: 4-7 DESIGN QUALITIES to research, phrased as what sites should communicate
  (e.g. "medical trust", "enterprise credibility", "scientific authority") — not keywords
Be concrete. No filler."""


class IntentAnalyzer:
    def __init__(self, llm: LLMClient):
        self.llm = llm

    async def analyze(self, request: str) -> ProjectIntent:
        proposal: dict = {}
        try:
            proposal = await self.llm.chat_json(
                "plan", _INTENT_SYSTEM, f"User request: {request}", _INTENT_SCHEMA)
        except LLMUnavailable:
            proposal = {}

        def _strs(key: str, fallback: list[str]) -> list[str]:
            vals = proposal.get(key)
            if not isinstance(vals, list):
                return fallback
            clean = [v.strip() for v in vals if isinstance(v, str) and v.strip()]
            return clean or fallback

        # ---- deterministic validation --------------------------------
        pages: list[PageKind] = []
        for p in _strs("required_pages", ["landing", "product", "about", "contact"]):
            try:
                kind = PageKind(p)
            except ValueError:
                continue
            if kind not in pages:
                pages.append(kind)
        if PageKind.LANDING not in pages:      # a site without a front door is not a site
            pages.insert(0, PageKind.LANDING)

        name = str(proposal.get("product_name") or "").strip()
        if not name:
            # derive something neutral from the request's capitalized words
            words = re.findall(r"[A-Za-z]{3,}", request)
            name = (words[0].capitalize() if words else "Untitled") + " Co"

        return ProjectIntent(
            raw_request=request,
            industry=str(proposal.get("industry") or "general").strip(),
            product_name=name[:40],
            audience=_strs("audience", ["general public"]),
            brand_position=_strs("brand_position", ["clear", "modern", "credible"]),
            user_goals=_strs("user_goals", ["credibility"]),
            required_pages=pages,
            semantic_traits=_strs("semantic_traits",
                                  ["clarity", "credibility", "modern design"]),
        )
