"""Typed design vocabulary — everything the pipeline passes between phases.

The load-bearing invariant mirrors research-engine's evidence chain, adapted
to design: every trait in the Context Graph points at a real analyzed
website (url, fetched_at); every synthesis decision cites the trait ids it
drew from; the generated site records which decisions produced it. Idea →
site is a provenance chain, queryable end to end.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


# --------------------------------------------------------------------------
# Phase 1 — intent
# --------------------------------------------------------------------------

class PageKind(str, Enum):
    LANDING = "landing"
    PRODUCT = "product"
    ABOUT = "about"
    PRICING = "pricing"
    CONTACT = "contact"
    DOCS = "docs"


class ProjectIntent(BaseModel):
    id: str = Field(default_factory=lambda: new_id("intent"))
    raw_request: str
    industry: str = ""
    audience: list[str] = Field(default_factory=list)
    brand_position: list[str] = Field(default_factory=list)   # e.g. trustworthy, advanced
    user_goals: list[str] = Field(default_factory=list)       # e.g. lead generation
    required_pages: list[PageKind] = Field(default_factory=list)
    semantic_traits: list[str] = Field(default_factory=list)  # the intent-not-keyword search axes
    product_name: str = ""
    created_at: datetime = Field(default_factory=now_utc)


# --------------------------------------------------------------------------
# Phase 2/3 — analyzed websites and extracted traits
# --------------------------------------------------------------------------

class TraitKind(str, Enum):
    LAYOUT = "layout"            # nav archetype, section ordering, grid density
    TYPOGRAPHY = "typography"    # font classes and pairings
    COLOR = "color"              # palette roles
    MOTION = "motion"            # animation presence/intensity
    COMPONENT = "component"      # detected component patterns
    CONVERSION = "conversion"    # CTA density, social proof, pricing presence
    TECHNOLOGY = "technology"    # framework fingerprints


class DesignTrait(BaseModel):
    """One abstract, non-copyrightable design observation about one site.
    Traits are the ONLY thing that flows from analyzed websites into
    synthesis — markup never crosses this boundary."""
    id: str = Field(default_factory=lambda: new_id("trait"))
    kind: TraitKind
    name: str                    # e.g. "minimal_nav", "geometric_sans", "dark_technical"
    value: str = ""              # detail, e.g. "5 links, no dropdowns" / "#0a0f1e"
    site_url: str
    confidence: float = 0.8      # extraction certainty (deterministic per rule)


class SiteAnalysis(BaseModel):
    """Deterministic DOM/CSS-level analysis of one fetched website."""
    url: str
    title: str = ""
    description: str = ""
    fetched_at: datetime = Field(default_factory=now_utc)
    ok: bool = True
    error: str = ""
    traits: list[DesignTrait] = Field(default_factory=list)
    fonts: list[str] = Field(default_factory=list)
    palette: list[str] = Field(default_factory=list)          # hex, most-used first
    nav_link_count: int = 0
    section_signals: list[str] = Field(default_factory=list)  # hero/testimonials/pricing/...
    frameworks: list[str] = Field(default_factory=list)
    worker: str = ""             # which research agent fetched it
    seed_category: str = ""      # award|saas|enterprise|startup|industry|competitor|""


# --------------------------------------------------------------------------
# Phase 5 — the synthesized design system (schema-gated LLM proposal)
# --------------------------------------------------------------------------

class FontClass(str, Enum):
    GEOMETRIC_SANS = "geometric_sans"
    HUMANIST_SANS = "humanist_sans"
    NEO_GROTESQUE = "neo_grotesque"
    SERIF_DISPLAY = "serif_display"
    MONO_ACCENT = "mono_accent"


class MotionLevel(str, Enum):
    NONE = "none"
    SUBTLE = "subtle"
    EXPRESSIVE = "expressive"


class Palette(BaseModel):
    """Five-role palette. Hex only; contrast is validated and auto-fixed
    deterministically (WCAG AA) after the LLM proposes."""
    background: str
    surface: str
    text: str
    muted: str
    accent: str


class SectionKind(str, Enum):
    NAV = "nav"
    HERO = "hero"
    LOGO_CLOUD = "logo_cloud"
    FEATURE_GRID = "feature_grid"
    PRODUCT_SHOWCASE = "product_showcase"
    STATS_BAND = "stats_band"
    TESTIMONIALS = "testimonials"
    PRICING = "pricing"
    FAQ = "faq"
    TEAM = "team"
    CONTACT_FORM = "contact_form"
    CTA = "cta"
    FOOTER = "footer"
    DOCS_LAYOUT = "docs_layout"
    TEXT_BLOCK = "text_block"


class PagePlan(BaseModel):
    kind: PageKind
    title: str
    sections: list[SectionKind]


class DesignSystem(BaseModel):
    id: str = Field(default_factory=lambda: new_id("ds"))
    project_intent_id: str = ""
    direction: str = ""                       # one-paragraph design rationale
    inspirations: list[dict] = Field(default_factory=list)  # [{site, trait, why}] — cited, never copied
    heading_font: FontClass = FontClass.GEOMETRIC_SANS
    body_font: FontClass = FontClass.HUMANIST_SANS
    palette: Palette
    dark_mode: bool = True
    radius_px: int = 12
    motion: MotionLevel = MotionLevel.SUBTLE
    pages: list[PagePlan] = Field(default_factory=list)
    brand_voice: str = ""                     # steer for the copywriter
    trait_ids: list[str] = Field(default_factory=list)  # provenance into the CG
    novelty_note: str = ""                    # filled by the anti-copy validator


# --------------------------------------------------------------------------
# Phase 7 — review
# --------------------------------------------------------------------------

class ReviewSeverity(str, Enum):
    BLOCKER = "blocker"
    WARNING = "warning"
    NOTE = "note"


class ReviewFinding(BaseModel):
    agent: str
    severity: ReviewSeverity
    code: str                    # machine-usable, e.g. "contrast_text_bg"
    message: str
    file: str = ""
    auto_fixable: bool = False


class ReviewReport(BaseModel):
    findings: list[ReviewFinding] = Field(default_factory=list)
    scores: dict[str, float] = Field(default_factory=dict)   # agent -> 0..100
    build_ok: bool | None = None            # None = build gate not run (no node)
    build_log_tail: str = ""

    @property
    def blockers(self) -> list[ReviewFinding]:
        return [f for f in self.findings if f.severity == ReviewSeverity.BLOCKER]


# --------------------------------------------------------------------------
# Phase 8 — the memory loop record
# --------------------------------------------------------------------------

class ProjectOutcome(BaseModel):
    """One honest row per generated site: what was chosen, what it scored.
    NO fabricated conversion data — real-world metrics enter only through
    the feedback endpoint when a human supplies them."""
    project_id: str
    industry: str
    design_system_id: str
    section_usage: dict[str, int] = Field(default_factory=dict)
    palette_mode: str = ""                   # dark|light
    heading_font: str = ""
    motion: str = ""
    review_scores: dict[str, float] = Field(default_factory=dict)
    build_ok: bool | None = None
    human_feedback: dict = Field(default_factory=dict)       # optional, user-supplied
    created_at: datetime = Field(default_factory=now_utc)


class GeneratedSite(BaseModel):
    project_id: str
    intent: ProjectIntent
    design_system: DesignSystem
    out_dir: str
    files_written: int = 0
    review: ReviewReport | None = None
    improve_rounds: int = 0
