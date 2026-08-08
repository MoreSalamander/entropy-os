"""Offline fixtures: a fake analyzed corpus and a ready DesignSystem.
The suite runs with no network, no Ollama, no node."""

from __future__ import annotations

import pytest

from entropy_os.engines.web.models import (DesignSystem, FontClass, MotionLevel,
                                  PageKind, PagePlan, Palette, ProjectIntent,
                                  SectionKind)
from entropy_os.engines.web.research.site_analyzer import SiteAnalyzer

FIXTURE_HTML = """<!doctype html><html><head>
<title>Acme Clinical — AI diagnostics</title>
<meta name="description" content="Trusted AI for hospitals">
<link href="https://fonts.googleapis.com/css2?family=Poppins:wght@600&family=Inter:wght@400&display=swap" rel="stylesheet">
<style>
body { font-family: Inter, sans-serif; background:#0a0f1e; color:#e8eaf2; }
h1 { font-family: Poppins, sans-serif; color:#e8eaf2; }
.btn { background:#4f8ff7; transition: transform .3s ease; }
.card { background:#131a2b; } .x{color:#0a0f1e}.y{background:#131a2b}.z{color:#4f8ff7}
@keyframes rise { from {opacity:0} to {opacity:1} }
</style><script>window.__NEXT_DATA__={}</script></head>
<body><header><nav><a href="/">Home</a><a href="/product">Product</a>
<a href="/pricing">Pricing</a><a href="/docs">Docs</a></nav></header>
<section class="hero"><h1>Trusted by clinicians</h1>
<a class="btn" href="/demo">Book a demo</a></section>
<section>Trusted by leading hospitals</section>
<section class="testimonial">“It works” — a customer</section>
<section>Pricing from $99 per month. SOC 2 and HIPAA ready.</section>
</body></html>"""


@pytest.fixture
def fixture_analysis():
    analyzer = SiteAnalyzer(client=None)
    return analyzer._analyze_html("https://acme-clinical.example", FIXTURE_HTML,
                                  worker="Test", seed_category="industry")


@pytest.fixture
def intent() -> ProjectIntent:
    return ProjectIntent(
        raw_request="Create a website for an AI healthcare startup",
        industry="Healthcare AI", product_name="Veritas Health",
        audience=["doctors", "hospitals", "investors"],
        brand_position=["trustworthy", "advanced", "scientific"],
        user_goals=["lead generation", "credibility"],
        required_pages=[PageKind.LANDING, PageKind.PRODUCT, PageKind.ABOUT,
                        PageKind.PRICING, PageKind.CONTACT, PageKind.DOCS],
        semantic_traits=["medical trust", "enterprise credibility",
                         "AI innovation", "scientific authority"])


@pytest.fixture
def design_system(intent) -> DesignSystem:
    return DesignSystem(
        project_intent_id=intent.id,
        direction="test direction",
        palette=Palette(background="#0b0f17", surface="#131a26", text="#e8edf5",
                        muted="#8b98ab", accent="#4f8ff7"),
        heading_font=FontClass.GEOMETRIC_SANS, body_font=FontClass.HUMANIST_SANS,
        dark_mode=True, motion=MotionLevel.SUBTLE,
        pages=[
            PagePlan(kind=PageKind.LANDING, title="Home", sections=[
                SectionKind.NAV, SectionKind.HERO, SectionKind.LOGO_CLOUD,
                SectionKind.FEATURE_GRID, SectionKind.PRODUCT_SHOWCASE,
                SectionKind.STATS_BAND, SectionKind.TESTIMONIALS,
                SectionKind.CTA, SectionKind.FOOTER]),
            PagePlan(kind=PageKind.PRODUCT, title="Product", sections=[
                SectionKind.NAV, SectionKind.HERO, SectionKind.FEATURE_GRID,
                SectionKind.FAQ, SectionKind.CTA, SectionKind.FOOTER]),
            PagePlan(kind=PageKind.ABOUT, title="About", sections=[
                SectionKind.NAV, SectionKind.TEXT_BLOCK, SectionKind.TEAM,
                SectionKind.CTA, SectionKind.FOOTER]),
            PagePlan(kind=PageKind.PRICING, title="Pricing", sections=[
                SectionKind.NAV, SectionKind.PRICING, SectionKind.FAQ,
                SectionKind.CTA, SectionKind.FOOTER]),
            PagePlan(kind=PageKind.CONTACT, title="Contact", sections=[
                SectionKind.NAV, SectionKind.CONTACT_FORM, SectionKind.FOOTER]),
            PagePlan(kind=PageKind.DOCS, title="Docs", sections=[
                SectionKind.NAV, SectionKind.DOCS_LAYOUT, SectionKind.FOOTER]),
        ])


async def write_demo_site(tmp_path, intent, design_system):
    """Offline generation helper: house copy (FakeLLM down) → full project."""
    from entropy_os.engines.research.llm.client import FakeLLM
    from entropy_os.engines.web.codegen.copywriter import Copywriter
    from entropy_os.engines.web.codegen.project_writer import _PAGE_HREFS, ProjectWriter

    copywriter = Copywriter(FakeLLM(up=False))
    hrefs = [_PAGE_HREFS[p.kind] for p in design_system.pages]
    copy = {}
    for plan in design_system.pages:
        copy[plan.kind.value] = await copywriter.write_page(
            intent, design_system, plan, hrefs)
    out = tmp_path / "site"
    return ProjectWriter(out).write(intent, design_system, copy), out
