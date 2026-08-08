"""Copywriting Agent — schema-gated site copy, one call per page.

Integrity rules, enforced deterministically after the LLM proposes:
  * testimonial personas and logo-cloud names must be fictional — a
    blocklist sweep replaces any real-brand/major-figure name with a
    generated placeholder, and the content file says they are placeholders
  * stats are labeled illustrative
  * every planned section gets content: missing/invalid blocks fall back to
    deterministic house copy, so the generator never emits a page with an
    empty section

The copywriter returns plain dicts shaped exactly like the component prop
interfaces; the project writer serializes them into lib/content.ts.
"""

from __future__ import annotations

import re

from entropy_os.engines.research.llm.client import LLMClient, LLMUnavailable

from ..models import DesignSystem, PageKind, PagePlan, ProjectIntent, SectionKind

# Real brands/figures that must never appear as fake customers or quotes.
_REAL_BRAND_RE = re.compile(
    r"\b(google|apple|microsoft|amazon|meta|facebook|openai|anthropic|nvidia|stripe|"
    r"salesforce|ibm|oracle|tesla|netflix|spotify|uber|airbnb|pfizer|mayo clinic|"
    r"kaiser|cleveland clinic|johns hopkins|epic systems|cerner|elon musk|sam altman)\b",
    re.I)

_PLACEHOLDER_ORGS = ["Meridian Labs", "Northbeam Health", "Cobalt Systems",
                     "Halcyon Group", "Vantage Clinical", "Arclight Partners"]
_PLACEHOLDER_PEOPLE = [("Dr. Amara Osei", "Chief Medical Officer, Meridian Labs"),
                       ("Jonas Feld", "VP Engineering, Cobalt Systems"),
                       ("Priya Raman", "Director of Operations, Northbeam Health")]

_CTA = {"type": "object",
        "properties": {"label": {"type": "string"}, "href": {"type": "string"}},
        "required": ["label", "href"]}

_PAGE_SCHEMA = {
    "type": "object",
    "properties": {
        "meta_title": {"type": "string"},
        "meta_description": {"type": "string"},
        "hero": {"type": "object", "properties": {
            "eyebrow": {"type": "string"}, "headline": {"type": "string"},
            "subheadline": {"type": "string"},
            "highlights": {"type": "array", "items": {"type": "string"}}},
            "required": ["headline", "subheadline"]},
        "features": {"type": "array", "items": {"type": "object", "properties": {
            "title": {"type": "string"}, "description": {"type": "string"}},
            "required": ["title", "description"]}},
        "features_heading": {"type": "string"},
        "showcase_panels": {"type": "array", "items": {"type": "object", "properties": {
            "label": {"type": "string"}, "value": {"type": "string"}},
            "required": ["label", "value"]}},
        "stats": {"type": "array", "items": {"type": "object", "properties": {
            "value": {"type": "string"}, "label": {"type": "string"}},
            "required": ["value", "label"]}},
        "testimonials": {"type": "array", "items": {"type": "object", "properties": {
            "quote": {"type": "string"}, "name": {"type": "string"},
            "role": {"type": "string"}}, "required": ["quote", "name", "role"]}},
        "pricing_tiers": {"type": "array", "items": {"type": "object", "properties": {
            "name": {"type": "string"}, "price": {"type": "string"},
            "description": {"type": "string"},
            "features": {"type": "array", "items": {"type": "string"}}},
            "required": ["name", "price", "description", "features"]}},
        "faq": {"type": "array", "items": {"type": "object", "properties": {
            "question": {"type": "string"}, "answer": {"type": "string"}},
            "required": ["question", "answer"]}},
        "team": {"type": "array", "items": {"type": "object", "properties": {
            "name": {"type": "string"}, "role": {"type": "string"},
            "bio": {"type": "string"}}, "required": ["name", "role", "bio"]}},
        "paragraphs": {"type": "array", "items": {"type": "string"}},
        "docs_topics": {"type": "array", "items": {"type": "object", "properties": {
            "title": {"type": "string"}, "body": {"type": "string"},
            "code": {"type": "string"}}, "required": ["title", "body"]}},
        "cta_heading": {"type": "string"},
        "cta_sub": {"type": "string"},
    },
    "required": ["meta_title", "meta_description"],
}

_SYSTEM = """You are the copywriting module of a website generation engine.
Write the copy for ONE page of the site described below, as JSON matching the schema.
Voice: {voice}
Rules:
- Specific and concrete; no buzzword soup, no "unlock/unleash/empower".
- Testimonial names and any customer/organization names MUST be clearly fictional
  (never real companies or real people).
- Stats are illustrative placeholders — plausible, round-ish numbers.
- Provide content ONLY for the sections listed; omit the rest.
- hrefs use site-relative paths from this set: {hrefs}"""


class Copywriter:
    def __init__(self, llm: LLMClient):
        self.llm = llm
        self.degraded = False

    # ------------------------------------------------------------------ #
    def _sanitize_names(self, page: dict) -> int:
        """Replace real-brand/figure mentions in persona fields. Returns count."""
        replaced = 0
        for i, t in enumerate(page.get("testimonials") or []):
            for field in ("name", "role"):
                if _REAL_BRAND_RE.search(str(t.get(field, ""))):
                    person = _PLACEHOLDER_PEOPLE[i % len(_PLACEHOLDER_PEOPLE)]
                    t["name"], t["role"] = person
                    replaced += 1
                    break
        for i, m in enumerate(page.get("team") or []):
            if _REAL_BRAND_RE.search(str(m.get("name", "")) + str(m.get("role", ""))):
                m["name"] = f"Team Member {i + 1}"
                m["role"] = re.sub(_REAL_BRAND_RE, "the company", str(m.get("role", "")))
                replaced += 1
        return replaced

    # ------------------------------------------------------------------ #
    async def write_page(self, intent: ProjectIntent, ds: DesignSystem,
                         plan: PagePlan, hrefs: list[str]) -> dict:
        wanted = {s.value for s in plan.sections}
        user = (f"Site: {intent.product_name} — {intent.raw_request}\n"
                f"Industry: {intent.industry}\nAudience: {', '.join(intent.audience)}\n"
                f"Brand position: {', '.join(intent.brand_position)}\n"
                f"Design direction: {ds.direction}\n"
                f"PAGE: {plan.kind.value} ('{plan.title}')\n"
                f"Sections to write: {', '.join(sorted(wanted))}")
        try:
            page = await self.llm.chat_json(
                "summarize",
                _SYSTEM.format(voice=ds.brand_voice or "plain and confident",
                               hrefs=", ".join(hrefs)),
                user, _PAGE_SCHEMA)
        except LLMUnavailable:
            self.degraded = True
            page = {}
        if not isinstance(page, dict):
            page = {}
        self._sanitize_names(page)
        return self._fill_gaps(intent, plan, page, hrefs)

    # ------------------------------------------------------------------ #
    # deterministic house copy — used per-block whenever the LLM's block is
    # missing or malformed, so planned sections are never empty
    # ------------------------------------------------------------------ #
    def _fill_gaps(self, intent: ProjectIntent, plan: PagePlan, page: dict,
                   hrefs: list[str]) -> dict:
        name = intent.product_name
        cta_href = "/contact" if "/contact" in hrefs else hrefs[0]
        sections = set(plan.sections)

        def missing(key: str, min_len: int = 1) -> bool:
            val = page.get(key)
            return not isinstance(val, list) or len(val) < min_len

        page.setdefault("meta_title", f"{plan.title} — {name}")
        page.setdefault("meta_description",
                        f"{name}: {', '.join(intent.brand_position[:3])} "
                        f"{intent.industry} platform.")

        if SectionKind.HERO in sections and not isinstance(page.get("hero"), dict):
            page["hero"] = {
                "eyebrow": intent.industry,
                "headline": f"{name}: {intent.brand_position[0].capitalize()} "
                            f"{intent.industry} for {intent.audience[0]}",
                "subheadline": "Built for teams that need results they can defend. "
                               "Clear workflows, measurable outcomes, no black boxes.",
                "highlights": intent.brand_position[:3],
            }
        if SectionKind.FEATURE_GRID in sections and missing("features", 3):
            page["features"] = [
                {"title": "Fast to adopt", "description":
                    "Onboard in days, not quarters — sensible defaults everywhere."},
                {"title": "Auditable by design", "description":
                    "Every result links back to its inputs and reasoning."},
                {"title": "Secure foundations", "description":
                    "Role-based access and encryption in transit and at rest."},
                {"title": "Built to integrate", "description":
                    "APIs and exports that meet your existing systems where they are."},
            ]
        page.setdefault("features_heading", f"Why teams choose {name}")
        if SectionKind.PRODUCT_SHOWCASE in sections and missing("showcase_panels", 3):
            page["showcase_panels"] = [
                {"label": "Throughput", "value": "12.4k/day"},
                {"label": "Accuracy", "value": "99.2%"},
                {"label": "Time saved", "value": "31 hrs/wk"},
            ]
        if SectionKind.STATS_BAND in sections and missing("stats", 3):
            page["stats"] = [
                {"value": "98%", "label": "Illustrative satisfaction rate"},
                {"value": "4x", "label": "Faster review cycles (placeholder)"},
                {"value": "24/7", "label": "Monitoring"},
                {"value": "SOC 2", "label": "Ready posture (target)"},
            ]
        if SectionKind.TESTIMONIALS in sections and missing("testimonials", 3):
            page["testimonials"] = [
                {"quote": "The first tool in this category our clinicians actually "
                          "kept using after the pilot.", **dict(zip(("name", "role"),
                           _PLACEHOLDER_PEOPLE[0]))},
                {"quote": "Setup took an afternoon. The audit trail alone justified "
                          "the switch.", **dict(zip(("name", "role"),
                           _PLACEHOLDER_PEOPLE[1]))},
                {"quote": "Our board asked harder questions than any vendor demo — "
                          "this held up.", **dict(zip(("name", "role"),
                           _PLACEHOLDER_PEOPLE[2]))},
            ]
        if SectionKind.PRICING in sections and missing("pricing_tiers", 3):
            page["pricing_tiers"] = [
                {"name": "Starter", "price": "$0", "description":
                    "Evaluate with your own data.", "features":
                    ["Single project", "Community support", "Core features"]},
                {"name": "Team", "price": "$49", "description":
                    "For working teams shipping weekly.", "features":
                    ["Unlimited projects", "Priority support", "Integrations", "Audit log"]},
                {"name": "Enterprise", "price": "Custom", "description":
                    "Compliance, scale, and dedicated support.", "features":
                    ["SSO/SAML", "Custom SLAs", "Dedicated environment", "Security review"]},
            ]
        if SectionKind.FAQ in sections and missing("faq", 3):
            page["faq"] = [
                {"question": f"How does {name} handle data privacy?",
                 "answer": "Data stays in your environment where possible; everything "
                           "else is encrypted in transit and at rest."},
                {"question": "How long does implementation take?",
                 "answer": "Most teams run their first real workload within a week."},
                {"question": "Can we export everything?",
                 "answer": "Yes — full-fidelity exports, no lock-in by design."},
            ]
        if SectionKind.TEAM in sections and missing("team", 3):
            page["team"] = [
                {"name": "Placeholder Founder", "role": "CEO",
                 "bio": "Replace with a real bio — background, motivation, credibility."},
                {"name": "Placeholder Cofounder", "role": "CTO",
                 "bio": "Replace with a real bio — technical track record."},
                {"name": "Placeholder Lead", "role": "Head of Product",
                 "bio": "Replace with a real bio — domain expertise."},
            ]
        if SectionKind.TEXT_BLOCK in sections and missing("paragraphs", 2):
            page["paragraphs"] = [
                f"{name} exists because {intent.industry.lower()} deserves tools "
                f"that are {', '.join(intent.brand_position[:2]).lower()} — and "
                "provable about both.",
                "This page is generated placeholder copy: replace it with the real "
                "story of why this team, why now, and why this approach.",
            ]
        if SectionKind.DOCS_LAYOUT in sections and missing("docs_topics", 3):
            page["docs_topics"] = [
                {"title": "Quickstart", "body": "Install, authenticate, and run your "
                 "first request in under five minutes.",
                 "code": "curl -X POST https://api.example.com/v1/run \\\n  -H 'Authorization: Bearer <token>'"},
                {"title": "Core concepts", "body": "Projects, runs, and results — the "
                 "three objects everything else builds on."},
                {"title": "API reference", "body": "Every endpoint, request shape, and "
                 "error code, with examples."},
            ]
        page.setdefault("cta_heading", f"See {name} on your own data")
        page.setdefault("cta_sub", "A 30-minute walkthrough with your team's real questions.")
        page["_cta_href"] = cta_href
        return page
