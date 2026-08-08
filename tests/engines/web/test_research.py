"""Intent analysis, site analysis, seeds — the research layer offline."""

from __future__ import annotations

from entropy_os.engines.research.llm.client import FakeLLM

from entropy_os.engines.web.models import PageKind, TraitKind
from entropy_os.engines.web.research.intent import IntentAnalyzer
from entropy_os.engines.web.research.seeds import SEED_SITES, seeds_for


class TestIntent:
    async def test_llm_down_yields_working_intent(self):
        intent = await IntentAnalyzer(FakeLLM(up=False)).analyze(
            "Create a website for an AI healthcare startup")
        assert PageKind.LANDING in intent.required_pages
        assert intent.semantic_traits
        assert intent.product_name

    async def test_landing_always_present_and_pages_validated(self):
        proposal = {"industry": "Healthcare AI", "product_name": "Acme",
                    "audience": ["doctors"], "brand_position": ["trustworthy"],
                    "user_goals": ["leads"],
                    "required_pages": ["pricing", "docs", "nonsense_page"],
                    "semantic_traits": ["medical trust"]}
        intent = await IntentAnalyzer(FakeLLM({"plan": [proposal]})).analyze("x")
        assert intent.required_pages[0] == PageKind.LANDING  # guaranteed front door
        assert PageKind.PRICING in intent.required_pages
        assert all(isinstance(p, PageKind) for p in intent.required_pages)


class TestSiteAnalyzer:
    def test_extracts_typography(self, fixture_analysis):
        names = {t.name for t in fixture_analysis.traits
                 if t.kind == TraitKind.TYPOGRAPHY}
        assert "geometric_sans" in names   # Poppins
        assert "humanist_sans" in names    # Inter

    def test_extracts_dark_palette(self, fixture_analysis):
        color = [t for t in fixture_analysis.traits if t.kind == TraitKind.COLOR]
        assert color and color[0].name == "dark_technical"
        assert "#0a0f1e" in fixture_analysis.palette

    def test_nav_archetype_and_sections(self, fixture_analysis):
        layout = {t.name for t in fixture_analysis.traits if t.kind == TraitKind.LAYOUT}
        assert "minimal_nav" in layout     # 4 links
        assert {"hero", "testimonials", "pricing", "logo_cloud", "cta",
                "security", "docs"} <= set(fixture_analysis.section_signals)

    def test_framework_fingerprints_and_motion(self, fixture_analysis):
        assert "nextjs" in fixture_analysis.frameworks
        motion = [t for t in fixture_analysis.traits if t.kind == TraitKind.MOTION]
        assert motion[0].name in ("motion_subtle", "motion_expressive")

    def test_title_and_meta(self, fixture_analysis):
        assert "Acme Clinical" in fixture_analysis.title
        assert fixture_analysis.description == "Trusted AI for hospitals"


class TestSeeds:
    def test_award_tier_always_included(self):
        picked = seeds_for("Gaming", ["immersive"])
        assert any(s["category"] == "award" for s in picked)

    def test_healthcare_pulls_industry_tier(self):
        picked = seeds_for("Healthcare AI", ["medical trust"])
        urls = {s["url"] for s in picked}
        assert any("mayoclinic" in u or "nih" in u or "tempus" in u for u in urls)

    def test_no_duplicates(self):
        picked = seeds_for("enterprise b2b healthcare", ["trust"])
        urls = [s["url"] for s in picked]
        assert len(urls) == len(set(urls))
        assert len(SEED_SITES) == len({s["url"] for s in SEED_SITES})
