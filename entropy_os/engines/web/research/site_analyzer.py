"""Deterministic DOM/CSS-level website analysis — the design-pattern extractor.

Fetches a live site and reduces it to ABSTRACT TRAITS: typography classes,
palette, nav archetype, section signals, motion signals, conversion
patterns, framework fingerprints. No LLM anywhere in this file — every
trait is a rule with a name, so two runs on the same HTML agree exactly.

The anti-copying boundary lives here: markup goes in, only DesignTrait
records come out. Nothing downstream ever sees a fetched site's HTML.
"""

from __future__ import annotations

import re
from collections import Counter

import httpx
from bs4 import BeautifulSoup

from ..models import DesignTrait, SiteAnalysis, TraitKind

# font-stack → font-class heuristics (first recognized family wins)
_FONT_CLASSES = [
    (r"futura|poppins|montserrat|raleway|circular|gilroy|sofia|geometr", "geometric_sans"),
    (r"inter|open sans|lato|source sans|noto sans|frutiger|segoe|system-ui|-apple-system", "humanist_sans"),
    (r"helvetica|arial|roboto(?!\s*(slab|mono))|aktiv|neue haas|suisse|univers", "neo_grotesque"),
    (r"georgia|garamond|playfair|freight|tiempos|canela|serif", "serif_display"),
    (r"mono|consolas|menlo|courier|jetbrains|fira code|ibm plex mono", "mono_accent"),
]

_SECTION_SIGNALS = {
    "hero": [r"\bhero\b", r"class=\"[^\"]*hero"],
    "testimonials": [r"testimonial", r"\bquote\b.{0,80}(customer|client)", r"what (our|their) (customers|clients|users)"],
    "pricing": [r"\bpricing\b", r"/pricing", r"per (month|user|seat)"],
    "logo_cloud": [r"trusted by", r"used by", r"customers include", r"logo-?(cloud|wall|grid)"],
    "faq": [r"\bfaq\b", r"frequently asked"],
    "stats": [r"\d{2,}[%+]|\b\d+(\.\d+)?[kmb]\+", r"class=\"[^\"]*stat"],
    "cta": [r"(get started|book a demo|request (a )?demo|start free|sign up|contact sales)"],
    "docs": [r"/docs\b", r"documentation"],
    "security": [r"\b(soc ?2|hipaa|gdpr|iso ?27001)\b"],
}

_FRAMEWORKS = {
    "nextjs": [r"/_next/", r"__NEXT_DATA__"],
    "react": [r"data-react", r"react-dom", r"__NEXT_DATA__"],
    "tailwind": [r"class=\"[^\"]*(?:flex|grid) [^\"]*(?:items-center|justify-between)[^\"]*\""],
    "gatsby": [r"___gatsby"],
    "vue_nuxt": [r"__NUXT__", r"data-v-[0-9a-f]{8}"],
    "wordpress": [r"wp-content"],
    "framer_or_webflow": [r"framerusercontent", r"website-files\.com"],
}

_HEX_RE = re.compile(r"#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b")
_FONT_FAMILY_RE = re.compile(r"font-family\s*:\s*([^;}{]+)[;}]", re.I)
_GOOGLE_FONT_RE = re.compile(r"fonts\.googleapis\.com/css2?\?[^\"']*family=([A-Za-z+0-9|:;,@.]+)")
_ANIMATION_RE = re.compile(r"@keyframes|animation\s*:|transition\s*:\s*[^;]{3,}|data-aos|framer-motion|motion-", re.I)


def _luminance(hex_color: str) -> float:
    """WCAG relative luminance; shared with the review layer's contrast math."""
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    try:
        r, g, b = (int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    except ValueError:
        return 0.5
    def lin(c: float) -> float:
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


class SiteAnalyzer:
    """One shared analyzer; fetching honors research-engine's containment
    rule — failures return SiteAnalysis(ok=False, error=...), never raise."""

    def __init__(self, client: httpx.AsyncClient):
        self.client = client

    async def analyze(self, url: str, worker: str = "",
                      seed_category: str = "") -> SiteAnalysis:
        try:
            r = await self.client.get(url)
            r.raise_for_status()
            html = r.text[:800_000]  # cap pathological pages
        except Exception as e:  # noqa: BLE001 — containment boundary
            return SiteAnalysis(url=url, ok=False, worker=worker,
                                seed_category=seed_category,
                                error=f"{type(e).__name__}: {e}"[:160])
        return self._analyze_html(url, html, worker, seed_category)

    # ------------------------------------------------------------------ #
    def _analyze_html(self, url: str, html: str, worker: str,
                      seed_category: str) -> SiteAnalysis:
        soup = BeautifulSoup(html, "html.parser")
        analysis = SiteAnalysis(url=url, worker=worker, seed_category=seed_category)
        analysis.title = (soup.title.get_text() if soup.title else "")[:200].strip()
        meta = soup.find("meta", attrs={"name": "description"})
        analysis.description = (meta.get("content", "") if meta else "")[:300]

        lower = html.casefold()
        t = analysis.traits.append  # local alias, this file appends a lot

        # ---- typography ------------------------------------------------
        families: list[str] = []
        for m in _FONT_FAMILY_RE.finditer(html):
            families.append(m.group(1).split(",")[0].strip(" '\""))
        for m in _GOOGLE_FONT_RE.finditer(html):
            families += [f.split(":")[0].replace("+", " ") for f in m.group(1).split("|")]
        analysis.fonts = [f for f, _n in Counter(
            f.casefold() for f in families if f and len(f) < 40).most_common(5)]
        seen_classes: set[str] = set()
        for fam in analysis.fonts:
            for pattern, cls in _FONT_CLASSES:
                if re.search(pattern, fam) and cls not in seen_classes:
                    seen_classes.add(cls)
                    t(DesignTrait(kind=TraitKind.TYPOGRAPHY, name=cls,
                                  value=fam, site_url=url))
                    break

        # ---- palette ---------------------------------------------------
        hexes = [h.casefold() for h in _HEX_RE.findall(html)]
        common = [h for h, n in Counter(hexes).most_common(24) if n >= 2][:8]
        analysis.palette = common
        if common:
            bg_dark = sum(1 for h in common[:4] if _luminance(h) < 0.25)
            mode = "dark_technical" if bg_dark >= 2 else "light_clean"
            t(DesignTrait(kind=TraitKind.COLOR, name=mode,
                          value=",".join(common[:5]), site_url=url))

        # ---- navigation archetype -------------------------------------
        nav = soup.find("nav") or soup.find("header")
        links = nav.find_all("a") if nav else []
        analysis.nav_link_count = len(links)
        if nav is not None:
            arche = ("minimal_nav" if len(links) <= 6
                     else "standard_nav" if len(links) <= 12 else "mega_nav")
            t(DesignTrait(kind=TraitKind.LAYOUT, name=arche,
                          value=f"{len(links)} links", site_url=url))

        # ---- section / conversion signals -----------------------------
        for signal, patterns in _SECTION_SIGNALS.items():
            if any(re.search(p, lower) for p in patterns):
                analysis.section_signals.append(signal)
                kind = (TraitKind.CONVERSION if signal in
                        ("cta", "pricing", "logo_cloud", "testimonials", "security")
                        else TraitKind.COMPONENT)
                t(DesignTrait(kind=kind, name=f"has_{signal}", site_url=url))

        # ---- motion ----------------------------------------------------
        # any transition/keyframe at all is motion; volume separates subtle
        # from expressive
        motion_hits = len(_ANIMATION_RE.findall(html))
        level = ("motion_expressive" if motion_hits > 40
                 else "motion_subtle" if motion_hits > 0 else "motion_none")
        t(DesignTrait(kind=TraitKind.MOTION, name=level,
                      value=str(motion_hits), site_url=url))

        # ---- framework fingerprints -----------------------------------
        for fw, patterns in _FRAMEWORKS.items():
            if any(re.search(p, html) for p in patterns):
                analysis.frameworks.append(fw)
                t(DesignTrait(kind=TraitKind.TECHNOLOGY, name=fw, site_url=url))

        return analysis
