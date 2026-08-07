"""Copywriter integrity, project generation, review agents, improver, KG loop."""

from __future__ import annotations

import json
import re

from research_engine.llm.client import FakeLLM
from research_engine.graphs.store import NetworkXJSONStore
from research_engine.graphs.vector_index import VectorIndex

from design_engine.codegen.copywriter import Copywriter
from design_engine.codegen.project_writer import _PAGE_HREFS
from design_engine.graphs.knowledge_graph import DesignKnowledgeGraph
from design_engine.models import (PageKind, ProjectOutcome, ReviewSeverity,
                                  SectionKind)
from design_engine.review.agents import run_review
from design_engine.review.improver import AutoImprover

from conftest import write_demo_site


class TestCopywriter:
    async def test_house_copy_covers_every_planned_section(self, intent, design_system):
        cw = Copywriter(FakeLLM(up=False))
        hrefs = [_PAGE_HREFS[p.kind] for p in design_system.pages]
        landing = next(p for p in design_system.pages if p.kind == PageKind.LANDING)
        copy = await cw.write_page(intent, design_system, landing, hrefs)
        assert copy["hero"]["headline"]
        assert len(copy["features"]) >= 3
        assert len(copy["testimonials"]) >= 3
        assert copy["meta_title"] and copy["meta_description"]
        assert cw.degraded is True

    async def test_real_brands_scrubbed_from_personas(self, intent, design_system):
        tainted = {"meta_title": "t", "meta_description": "d",
                   "testimonials": [
                       {"quote": "great", "name": "Sundar P.",
                        "role": "CEO, Google"},
                       {"quote": "fine", "name": "Jane Doe",
                        "role": "CTO, Meridian Labs"},
                       {"quote": "ok", "name": "Sam Altman", "role": "CEO"}]}
        cw = Copywriter(FakeLLM({"summarize": [tainted]}))
        landing = next(p for p in design_system.pages if p.kind == PageKind.LANDING)
        copy = await cw.write_page(intent, design_system, landing,
                                   ["/", "/contact"])
        blob = json.dumps(copy["testimonials"]).casefold()
        assert "google" not in blob
        assert "sam altman" not in blob
        assert "meridian labs" in blob  # fictional placeholder untouched


class TestProjectWriter:
    async def test_full_project_tree(self, tmp_path, intent, design_system):
        site, out = await write_demo_site(tmp_path, intent, design_system)
        for required in ("package.json", "tsconfig.json", "next.config.mjs",
                         "postcss.config.mjs", "app/globals.css",
                         "app/layout.tsx", "app/page.tsx", "app/sitemap.ts",
                         "app/robots.ts", "lib/content.ts",
                         "components/Hero.tsx", "components/NavBar.tsx"):
            assert (out / required).exists(), f"missing {required}"
        assert (out / "app/pricing/page.tsx").exists()
        assert (out / "app/docs/page.tsx").exists()
        assert site.files_written >= 25

    async def test_tokens_and_fonts_in_globals(self, tmp_path, intent, design_system):
        _site, out = await write_demo_site(tmp_path, intent, design_system)
        css = (out / "app/globals.css").read_text()
        assert "--color-background: #0b0f17" in css
        assert '--font-heading: "Poppins"' in css
        assert "prefers-reduced-motion" in css
        layout = (out / "app/layout.tsx").read_text()
        assert "display=swap" in layout and "Poppins" in layout

    async def test_pages_compose_planned_sections(self, tmp_path, intent, design_system):
        _site, out = await write_demo_site(tmp_path, intent, design_system)
        landing = (out / "app/page.tsx").read_text()
        for component in ("Hero", "LogoCloud", "FeatureGrid", "ProductShowcase",
                          "StatsBand", "Testimonials", "Cta"):
            assert f"<{component} " in landing
        contact = (out / "app/contact/page.tsx").read_text()
        assert "<ContactForm " in contact and "<Hero " not in contact

    async def test_content_ts_is_valid_and_placeholder_labeled(
            self, tmp_path, intent, design_system):
        _site, out = await write_demo_site(tmp_path, intent, design_system)
        ts = (out / "lib/content.ts").read_text()
        body = re.search(r"const content = (\{.*\}) as const;", ts, re.S).group(1)
        content = json.loads(body)  # JSON literal == valid TS literal
        assert content["siteConfig"]["brand"] == "Veritas Health"
        assert "placeholder" in ts.casefold()  # honesty labels present
        assert "null" not in body              # nulls never reach TS


class TestReviewAndImprove:
    async def test_generated_site_passes_clean(self, tmp_path, intent, design_system):
        _site, out = await write_demo_site(tmp_path, intent, design_system)
        report = run_review(out, design_system)
        assert report.blockers == [], [f.message for f in report.blockers]
        assert all(score >= 80 for score in report.scores.values()), report.scores

    async def test_seeded_defects_flagged_and_autofixed(
            self, tmp_path, intent, design_system):
        _site, out = await write_demo_site(tmp_path, intent, design_system)
        # sabotage: unreadable text token + bare img + unlabeled external link
        css_path = out / "app/globals.css"
        css_path.write_text(css_path.read_text()
                            .replace("--color-text: #e8edf5",
                                     "--color-text: #20242c")
                            .replace("@media (prefers-reduced-motion", "@media (pr-disabled"))
        hero = out / "components/Hero.tsx"
        hero.write_text(hero.read_text().replace(
            "<section className=\"hero-wash relative overflow-hidden\">",
            "<section className=\"hero-wash relative overflow-hidden\">"
            "<img src=\"/x.svg\" /><a href=\"https://example.org\">ext</a>"))

        report = run_review(out, design_system)
        codes = {f.code for f in report.findings}
        assert "contrast_text_background" in codes
        assert "img_no_alt" in codes
        assert "extlink_no_rel" in codes
        before = dict(report.scores)

        improved, rounds = AutoImprover().improve(out, design_system, report)
        assert rounds >= 1
        improved_codes = {f.code for f in improved.findings}
        assert "contrast_text_background" not in improved_codes
        assert "img_no_alt" not in improved_codes
        assert "extlink_no_rel" not in improved_codes
        for agent, score in improved.scores.items():
            assert score >= before[agent]  # monotone improvement


class TestKnowledgeGraphLoop:
    async def test_absorb_priors_and_scored_memory(self, tmp_path, fixture_analysis):
        kg = DesignKnowledgeGraph(
            NetworkXJSONStore(tmp_path / "kg.json"),
            VectorIndex(FakeLLM(), path=tmp_path / "q"))
        await kg.absorb_analysis(fixture_analysis, "Healthcare AI")
        priors = kg.priors_for("Healthcare AI")
        assert priors["trait_counts"].get("dark_technical") == 1
        assert priors["trait_counts"].get("minimal_nav") == 1

        kg.record_outcome(ProjectOutcome(
            project_id="p1", industry="Healthcare AI", design_system_id="ds1",
            section_usage={"hero": 2, "pricing": 1}, palette_mode="dark",
            heading_font="geometric_sans", motion="subtle",
            review_scores={"UX Agent": 90.0, "Design Agent": 100.0}))
        priors2 = kg.priors_for("Healthcare AI")
        assert priors2["past_projects"] == 1
        assert priors2["section_weight"]["hero"] > priors2["section_weight"]["pricing"]

    async def test_semantic_match_ranks_fingerprint(self, tmp_path, fixture_analysis):
        kg = DesignKnowledgeGraph(
            NetworkXJSONStore(tmp_path / "kg.json"),
            VectorIndex(FakeLLM(), path=tmp_path / "q"))
        await kg.absorb_analysis(fixture_analysis, "Healthcare AI")
        hits = await kg.semantic_match(["medical trust"], limit=3)
        assert isinstance(hits, list)  # FakeLLM hash-embeds: plumbing, not semantics

    async def test_feedback_requires_recorded_project(self, tmp_path):
        kg = DesignKnowledgeGraph(
            NetworkXJSONStore(tmp_path / "kg.json"),
            VectorIndex(FakeLLM(), path=tmp_path / "q"))
        assert kg.record_feedback("ghost", {"liked": True}) is False
