"""Phase 5 — Design Synthesis Engine.

Produces a DesignSystem from the Context Graph + Knowledge Graph priors.
Synthesis, not copying, is enforced structurally:

  1. deterministic code assembles the EVIDENCE BRIEF: trait census across
     the whole corpus, palette pools by mode, section priors, KG industry
     priors, semantic-match ranking — aggregate statistics, never one
     site's design;
  2. the LLM proposes a design direction through a schema gate (fonts,
     palette hexes, motion, per-page section plans, inspirations with
     cited sites + WHY);
  3. deterministic validators then decide: WCAG contrast auto-fix,
     novelty gate vs every source palette (a too-derivative palette is
     mutated away from its nearest source, and the note says so), page
     plans completed against required pages, section sanity (nav first,
     footer last, hero on landing).

If the LLM is down, a deterministic house-style fallback still yields a
buildable DesignSystem — degraded and labeled, never broken.
"""

from __future__ import annotations

from research_engine.llm.client import LLMClient, LLMUnavailable

from ..graphs.context_graph import DesignContextGraph
from ..models import (DesignSystem, FontClass, MotionLevel, PageKind,
                      PagePlan, Palette, ProjectIntent, SectionKind, TraitKind)
from .validators import fix_palette_contrast, novelty_check

_HEX = {"type": "string", "pattern": "^#[0-9a-fA-F]{6}$"}

_DESIGN_SCHEMA = {
    "type": "object",
    "properties": {
        "direction": {"type": "string"},
        "brand_voice": {"type": "string"},
        "heading_font": {"type": "string", "enum": [f.value for f in FontClass]},
        "body_font": {"type": "string", "enum": [f.value for f in FontClass]},
        "dark_mode": {"type": "boolean"},
        "motion": {"type": "string", "enum": [m.value for m in MotionLevel]},
        "palette": {
            "type": "object",
            "properties": {"background": _HEX, "surface": _HEX, "text": _HEX,
                           "muted": _HEX, "accent": _HEX},
            "required": ["background", "surface", "text", "muted", "accent"],
        },
        "inspirations": {
            "type": "array",
            "items": {"type": "object",
                      "properties": {"site": {"type": "string"},
                                     "trait": {"type": "string"},
                                     "why": {"type": "string"}},
                      "required": ["site", "trait", "why"]},
        },
        "pages": {
            "type": "array",
            "items": {"type": "object",
                      "properties": {
                          "kind": {"type": "string",
                                   "enum": [p.value for p in PageKind]},
                          "title": {"type": "string"},
                          "sections": {"type": "array",
                                       "items": {"type": "string",
                                                 "enum": [s.value for s in SectionKind]}},
                      },
                      "required": ["kind", "title", "sections"]},
        },
    },
    "required": ["direction", "brand_voice", "heading_font", "body_font",
                 "dark_mode", "motion", "palette", "inspirations", "pages"],
}

_SYSTEM = """You are the design-synthesis module of a website generation engine.
You receive an EVIDENCE BRIEF: aggregate design statistics from many analyzed
websites plus the project's intent. Propose ONE original design direction as JSON.

Rules:
- SYNTHESIZE across the corpus; never reproduce a single site's design.
- inspirations: 2-4 entries, each citing a DIFFERENT analyzed site, naming the
  abstract trait you draw from it and why it serves THIS project's audience.
- palette: 5 hex colors coherent with the brand position (background, surface,
  text, muted, accent). Surface sits near background; accent carries the brand.
- pages: a plan for EVERY required page. Landing starts with nav+hero and ends
  with cta+footer. Use sections that the evidence says this industry expects.
- brand_voice: 1-2 sentences steering the copywriter.
Be decisive. No filler."""

# deterministic house fallback (LLM down): quietly competent, clearly labeled
_FALLBACK = {
    "direction": "House fallback: restrained dark-technical enterprise style "
                 "(LLM unavailable — deterministic defaults).",
    "brand_voice": "Plain, confident, specific. Short sentences.",
    "heading_font": "geometric_sans", "body_font": "humanist_sans",
    "dark_mode": True, "motion": "subtle",
    "palette": {"background": "#0b0f17", "surface": "#131a26", "text": "#e8edf5",
                "muted": "#8b98ab", "accent": "#4f8ff7"},
    "inspirations": [], "pages": [],
}

_DEFAULT_SECTIONS: dict[PageKind, list[SectionKind]] = {
    PageKind.LANDING: [SectionKind.NAV, SectionKind.HERO, SectionKind.LOGO_CLOUD,
                       SectionKind.FEATURE_GRID, SectionKind.PRODUCT_SHOWCASE,
                       SectionKind.STATS_BAND, SectionKind.TESTIMONIALS,
                       SectionKind.CTA, SectionKind.FOOTER],
    PageKind.PRODUCT: [SectionKind.NAV, SectionKind.HERO, SectionKind.FEATURE_GRID,
                       SectionKind.PRODUCT_SHOWCASE, SectionKind.FAQ,
                       SectionKind.CTA, SectionKind.FOOTER],
    PageKind.ABOUT: [SectionKind.NAV, SectionKind.TEXT_BLOCK, SectionKind.TEAM,
                     SectionKind.STATS_BAND, SectionKind.CTA, SectionKind.FOOTER],
    PageKind.PRICING: [SectionKind.NAV, SectionKind.PRICING, SectionKind.FAQ,
                       SectionKind.CTA, SectionKind.FOOTER],
    PageKind.CONTACT: [SectionKind.NAV, SectionKind.CONTACT_FORM, SectionKind.FOOTER],
    PageKind.DOCS: [SectionKind.NAV, SectionKind.DOCS_LAYOUT, SectionKind.FOOTER],
}


class DesignSynthesizer:
    def __init__(self, llm: LLMClient):
        self.llm = llm

    # ------------------------------------------------------------------ #
    def _evidence_brief(self, cg: DesignContextGraph, priors: dict,
                        semantic_ranked: list[tuple[str, float]]) -> str:
        census = cg.trait_census()
        sections = cg.section_prior()
        pool = cg.palette_pool()
        lines = [
            f"PROJECT: {cg.intent.raw_request}",
            f"Industry: {cg.intent.industry} | Audience: {', '.join(cg.intent.audience)}",
            f"Brand position: {', '.join(cg.intent.brand_position)}",
            f"Goals: {', '.join(cg.intent.user_goals)}",
            f"Required pages: {', '.join(p.value for p in cg.intent.required_pages)}",
            "",
            f"CORPUS: {sum(1 for a in cg.analyses.values() if a.ok)} sites analyzed",
            "Trait census (name: count): " +
            ", ".join(f"{n}:{c}" for n, c in census.most_common(18)),
            "Section usage: " +
            ", ".join(f"{n}:{c}" for n, c in sections.most_common(12)),
            f"Palette modes observed: dark={len(pool.get('dark', []))} "
            f"light={len(pool.get('light', []))}",
        ]
        if priors.get("trait_counts"):
            lines.append("KG industry priors: " + ", ".join(
                f"{n}:{c}" for n, c in sorted(priors["trait_counts"].items(),
                                              key=lambda kv: -kv[1])[:10]))
        if priors.get("section_weight"):
            lines.append("KG scored-history section weights: " + ", ".join(
                f"{n}:{w:.1f}" for n, w in sorted(priors["section_weight"].items(),
                                                  key=lambda kv: -kv[1])[:8]))
        if semantic_ranked:
            lines.append("Semantic-match ranking (best first): " + ", ".join(
                f"{sid.removeprefix('website:')}" for sid, _s in semantic_ranked[:6]))
        good_sites = [a for a in cg.analyses.values() if a.ok][:12]
        lines.append("Analyzed sites available for inspiration citations: " +
                     ", ".join(a.url for a in good_sites))
        return "\n".join(lines)

    # ------------------------------------------------------------------ #
    async def synthesize(self, cg: DesignContextGraph, priors: dict,
                         semantic_ranked: list[tuple[str, float]]) -> DesignSystem:
        brief = self._evidence_brief(cg, priors, semantic_ranked)
        try:
            proposal = await self.llm.chat_json("plan", _SYSTEM, brief, _DESIGN_SCHEMA)
        except LLMUnavailable:
            proposal = dict(_FALLBACK)

        # ---- deterministic assembly + gates --------------------------
        def _enum(cls, value, default):
            try:
                return cls(value)
            except (ValueError, TypeError):
                return default

        pal_raw = proposal.get("palette") or _FALLBACK["palette"]
        try:
            palette = Palette(**{k: str(pal_raw.get(k, "#888888"))
                                 for k in ("background", "surface", "text",
                                           "muted", "accent")})
        except Exception:  # malformed hexes → fallback palette
            palette = Palette(**_FALLBACK["palette"])

        palette, contrast_fixes = fix_palette_contrast(palette)

        inspirations = [i for i in (proposal.get("inspirations") or [])
                        if isinstance(i, dict) and i.get("site")][:4]
        source_palettes = {url: a.palette for url, a in cg.analyses.items() if a.ok}
        ok, note = novelty_check(palette, source_palettes,
                                 [i["site"] for i in inspirations])
        if not ok:
            # deterministic de-derivation: rotate the accent hue away and
            # re-gate; if still derivative, fall back to house palette
            palette = Palette(background=palette.background, surface=palette.surface,
                              text=palette.text, muted=palette.muted,
                              accent=_rotate_hex(palette.accent))
            palette, extra = fix_palette_contrast(palette)
            contrast_fixes += extra
            ok2, note2 = novelty_check(palette, source_palettes,
                                       [i["site"] for i in inspirations])
            note = f"de-derived: {note} → {note2}"
            if not ok2:
                palette = Palette(**_FALLBACK["palette"])
                note = f"{note}; reverted to house palette"

        # page plans: every required page gets a plan; missing/invalid ones
        # come from defaults; landing invariants enforced
        proposed = {p.get("kind"): p for p in (proposal.get("pages") or [])
                    if isinstance(p, dict)}
        pages: list[PagePlan] = []
        for kind in cg.intent.required_pages:
            raw = proposed.get(kind.value, {})
            sections: list[SectionKind] = []
            for s in raw.get("sections", []):
                sk = _enum(SectionKind, s, None)
                if sk and sk not in sections:
                    sections.append(sk)
            if len(sections) < 3:
                sections = list(_DEFAULT_SECTIONS[kind])
            if sections[0] != SectionKind.NAV:
                sections.insert(0, SectionKind.NAV)
            if sections[-1] != SectionKind.FOOTER:
                sections.append(SectionKind.FOOTER)
            if kind == PageKind.LANDING and SectionKind.HERO not in sections:
                sections.insert(1, SectionKind.HERO)
            # titles are navigation-grade labels, not meta descriptions: clamp
            # verbose/templated LLM titles ("[Product Name]: Revolutionizing…")
            # back to the canonical page name
            title = str(raw.get("title") or "").strip()
            if not (2 <= len(title) <= 24) or "[" in title or ":" in title:
                title = kind.value.title()
            pages.append(PagePlan(kind=kind, title=title, sections=sections))

        ds = DesignSystem(
            project_intent_id=cg.intent.id,
            direction=str(proposal.get("direction") or _FALLBACK["direction"])[:600],
            inspirations=inspirations,
            heading_font=_enum(FontClass, proposal.get("heading_font"),
                               FontClass.GEOMETRIC_SANS),
            body_font=_enum(FontClass, proposal.get("body_font"),
                            FontClass.HUMANIST_SANS),
            palette=palette,
            dark_mode=bool(proposal.get("dark_mode", True)),
            radius_px=12,
            motion=_enum(MotionLevel, proposal.get("motion"), MotionLevel.SUBTLE),
            pages=pages,
            brand_voice=str(proposal.get("brand_voice") or "")[:300],
            trait_ids=list(cg.traits.keys()),
            novelty_note=note + (f"; contrast fixes: {len(contrast_fixes)}"
                                 if contrast_fixes else ""),
        )
        return ds


def _rotate_hex(hex_color: str) -> str:
    """Rotate a color's channels (r,g,b)→(b,r,g): a cheap deterministic hue
    shift that moves the accent away from whatever it was tracking."""
    h = hex_color.lstrip("#")
    if len(h) != 6:
        return "#4f8ff7"
    return f"#{h[4:6]}{h[0:2]}{h[2:4]}"
