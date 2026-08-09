"""Curated seed corpus — the honest answer to "award-winning websites" when
no awards API exists.

Every entry is a real, publicly reachable site chosen for a documented
design reputation (award wins, industry-reference status, or category
leadership). The engine FETCHES AND ANALYZES these live — nothing about
their design is hardcoded; if a site redesigns, the next analysis sees the
new design. Seeds are a starting corpus, not a ceiling: every project's
competitor/industry discoveries and any keyed web-search results join the
same Knowledge Graph and are searched semantically alongside these.

Categories mirror the spec's research-source taxonomy.
"""

from __future__ import annotations

SEED_SITES: list[dict] = [
    # -- award-winning / design-reference tier --------------------------
    {"url": "https://www.apple.com", "category": "award",
     "why": "minimalism reference; repeated design-award recognition"},
    {"url": "https://stripe.com", "category": "award",
     "why": "developer-focused clarity; canonical SaaS design reference"},
    {"url": "https://linear.app", "category": "award",
     "why": "modern product-site craft; motion + typography reference"},
    {"url": "https://vercel.com", "category": "award",
     "why": "dark technical aesthetic; frontend-industry reference"},
    {"url": "https://www.awwwards.com", "category": "award",
     "why": "the award venue itself; trend signal in its showcased work"},
    # -- SaaS ------------------------------------------------------------
    {"url": "https://www.notion.com", "category": "saas",
     "why": "friendly-productivity positioning; illustration-led"},
    {"url": "https://slack.com", "category": "saas",
     "why": "enterprise-friendly warmth; conversion-page patterns"},
    {"url": "https://www.figma.com", "category": "saas",
     "why": "creative-tool positioning; community proof patterns"},
    {"url": "https://tailwindcss.com", "category": "saas",
     "why": "docs-forward developer marketing"},
    # -- enterprise ------------------------------------------------------
    {"url": "https://www.salesforce.com", "category": "enterprise",
     "why": "classic enterprise trust patterns; heavy social proof"},
    {"url": "https://www.ibm.com", "category": "enterprise",
     "why": "institutional authority; design-system rigor (Carbon)"},
    {"url": "https://aws.amazon.com", "category": "enterprise",
     "why": "density + documentation-led enterprise selling"},
    # -- startup / AI-forward -------------------------------------------
    {"url": "https://openai.com", "category": "startup",
     "why": "AI-lab credibility; restrained scientific aesthetic"},
    {"url": "https://www.anthropic.com", "category": "startup",
     "why": "research-forward trust positioning"},
    {"url": "https://huggingface.co", "category": "startup",
     "why": "community-led AI branding; playful-technical balance"},
    # -- industry leaders (health/med for the healthcare axis) ----------
    {"url": "https://www.mayoclinic.org", "category": "industry",
     "why": "medical trust reference; accessibility-first institutional design"},
    {"url": "https://www.nih.gov", "category": "industry",
     "why": "scientific authority; government-grade information design"},
    {"url": "https://www.tempus.com", "category": "industry",
     "why": "AI-healthcare positioning in the wild"},
]


def seeds_for(industry: str, semantic_traits: list[str]) -> list[dict]:
    """Deterministic seed selection: always the award/reference tier, plus
    category tiers weighted by intent. Industry-tier seeds join when the
    industry text overlaps their why/url (crude, honest, and superseded as
    the KG accumulates real industry corpora)."""
    hay = (industry + " " + " ".join(semantic_traits)).casefold()
    picked = [s for s in SEED_SITES if s["category"] in ("award", "saas", "startup")]
    for s in SEED_SITES:
        if s["category"] in ("enterprise", "industry"):
            tokens = [t for t in (s["why"] + " " + s["url"]).casefold().split() if len(t) > 4]
            if any(t in hay for t in ("enterprise", "b2b", "corporate")) and s["category"] == "enterprise":
                picked.append(s)
            elif any(t[:6] in hay for t in tokens):
                picked.append(s)
    # dedupe preserving order
    seen: set[str] = set()
    return [s for s in picked if not (s["url"] in seen or seen.add(s["url"]))]
