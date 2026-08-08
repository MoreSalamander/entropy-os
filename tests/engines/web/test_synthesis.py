"""Validators and the synthesis gates."""

from __future__ import annotations

from entropy_os.engines.research.llm.client import FakeLLM

from entropy_os.engines.web.graphs.context_graph import DesignContextGraph
from entropy_os.engines.web.models import PageKind, Palette, SectionKind
from entropy_os.engines.web.synthesis.synthesizer import DesignSynthesizer
from entropy_os.engines.web.synthesis.validators import (contrast_ratio,
                                                fix_palette_contrast,
                                                novelty_check)


class TestContrast:
    def test_ratio_math(self):
        assert abs(contrast_ratio("#ffffff", "#000000") - 21.0) < 0.1
        assert abs(contrast_ratio("#777777", "#777777") - 1.0) < 0.01

    def test_fix_guarantees_aa(self):
        bad = Palette(background="#202020", surface="#262626", text="#3a3a3a",
                      muted="#2e2e2e", accent="#252525")
        fixed, changes = fix_palette_contrast(bad)
        assert changes  # it had to work
        assert contrast_ratio(fixed.text, fixed.background) >= 4.5
        assert contrast_ratio(fixed.muted, fixed.background) >= 4.5
        assert contrast_ratio(fixed.accent, fixed.background) >= 3.0
        assert contrast_ratio(fixed.text, fixed.surface) >= 4.5

    def test_good_palette_untouched(self):
        good = Palette(background="#0b0f17", surface="#131a26", text="#e8edf5",
                       muted="#9aa7ba", accent="#6fa8ff")
        _fixed, changes = fix_palette_contrast(good)
        assert changes == []


class TestNovelty:
    def test_rejects_single_source_palette(self):
        stolen = Palette(background="#0a0f1e", surface="#131a2b", text="#e8eaf2",
                         muted="#8b98ab", accent="#4f8ff7")
        sources = {"https://victim.example":
                   ["#0a0f1e", "#131a2b", "#e8eaf2", "#4f8ff7"]}
        ok, note = novelty_check(stolen, sources, ["https://victim.example"])
        assert not ok
        assert "victim" in note

    def test_accepts_synthesized_palette(self):
        novel = Palette(background="#101418", surface="#1a2028", text="#eef2f6",
                        muted="#93a1b0", accent="#37b58c")
        sources = {"https://a.example": ["#0a0f1e", "#4f8ff7"],
                   "https://b.example": ["#ffffff", "#111111"]}
        ok, note = novelty_check(novel, sources,
                                 ["https://a.example", "https://b.example"])
        assert ok
        assert "novel" in note


def _cg(intent, fixture_analysis):
    cg = DesignContextGraph("proj_test", intent)
    cg.add_analysis("Visual Design Agent", fixture_analysis)
    return cg


class TestSynthesizer:
    async def test_llm_down_yields_buildable_system(self, intent, fixture_analysis):
        ds = await DesignSynthesizer(FakeLLM(up=False)).synthesize(
            _cg(intent, fixture_analysis), {}, [])
        assert len(ds.pages) == len(intent.required_pages)  # every required page planned
        landing = next(p for p in ds.pages if p.kind == PageKind.LANDING)
        assert landing.sections[0] == SectionKind.NAV
        assert SectionKind.HERO in landing.sections
        assert landing.sections[-1] == SectionKind.FOOTER
        assert contrast_ratio(ds.palette.text, ds.palette.background) >= 4.5

    async def test_derivative_proposal_is_de_derived(self, intent, fixture_analysis):
        # LLM proposes exactly the analyzed site's palette → gate must react
        proposal = {
            "direction": "d", "brand_voice": "v",
            "heading_font": "geometric_sans", "body_font": "humanist_sans",
            "dark_mode": True, "motion": "subtle",
            "palette": {"background": "#0a0f1e", "surface": "#131a2b",
                        "text": "#e8eaf2", "muted": "#8b98ab", "accent": "#4f8ff7"},
            "inspirations": [{"site": "https://acme-clinical.example",
                              "trait": "dark palette", "why": "w"}],
            "pages": [],
        }
        ds = await DesignSynthesizer(FakeLLM({"plan": [proposal]})).synthesize(
            _cg(intent, fixture_analysis), {}, [])
        assert "de-derived" in ds.novelty_note or "house palette" in ds.novelty_note
        # whatever the outcome, contrast still holds
        assert contrast_ratio(ds.palette.text, ds.palette.background) >= 4.5

    async def test_invalid_sections_replaced_and_ordered(self, intent, fixture_analysis):
        proposal = {
            "direction": "d", "brand_voice": "v",
            "heading_font": "serif_display", "body_font": "humanist_sans",
            "dark_mode": False, "motion": "expressive",
            "palette": {"background": "#ffffff", "surface": "#f4f6f8",
                        "text": "#111418", "muted": "#5a6570", "accent": "#0a63c9"},
            "inspirations": [{"site": "https://a", "trait": "t", "why": "w"},
                             {"site": "https://b", "trait": "t", "why": "w"}],
            "pages": [{"kind": "landing", "title": "Home",
                       "sections": ["footer", "hero"]}],  # too short + wrong order
        }
        ds = await DesignSynthesizer(FakeLLM({"plan": [proposal]})).synthesize(
            _cg(intent, fixture_analysis), {}, [])
        landing = next(p for p in ds.pages if p.kind == PageKind.LANDING)
        assert len(landing.sections) >= 5              # defaults replaced the stub
        assert landing.sections[0] == SectionKind.NAV
        assert landing.sections[-1] == SectionKind.FOOTER
