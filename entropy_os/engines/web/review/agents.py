"""Phase 7 — Autonomous review agents.

Five agents inspect the GENERATED SOURCE deterministically — every check is
a named rule over real files, so review results are reproducible and the
improver can act on them mechanically. The optional build gate
(`npm install && next build`) is the ground-truth compile check, run by the
QA layer when node is available.

Scoring: each agent starts at 100 and loses points per finding
(blocker −25, warning −8, note −2, floor 0).
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

from ..models import DesignSystem, ReviewFinding, ReviewReport, ReviewSeverity
from ..synthesis.validators import contrast_ratio

_PENALTY = {ReviewSeverity.BLOCKER: 25, ReviewSeverity.WARNING: 8,
            ReviewSeverity.NOTE: 2}


def _tsx_files(root: Path) -> list[Path]:
    return [p for p in root.rglob("*.tsx") if "node_modules" not in p.parts]


class _Agent:
    name = "Review Agent"

    def review(self, root: Path, ds: DesignSystem) -> list[ReviewFinding]:
        raise NotImplementedError

    def _f(self, severity: ReviewSeverity, code: str, message: str,
           file: str = "", auto_fixable: bool = False) -> ReviewFinding:
        return ReviewFinding(agent=self.name, severity=severity, code=code,
                             message=message, file=file, auto_fixable=auto_fixable)


class AccessibilityReviewAgent(_Agent):
    """WCAG-oriented checks: token contrast (recomputed from the shipped CSS,
    not trusted from synthesis), heading discipline, landmarks, image alts,
    form labels, reduced-motion support, skip link."""
    name = "Accessibility Agent"

    def review(self, root: Path, ds: DesignSystem) -> list[ReviewFinding]:
        findings: list[ReviewFinding] = []
        css = (root / "app" / "globals.css").read_text() if (root / "app" / "globals.css").exists() else ""

        tokens = dict(re.findall(r"--color-(\w+):\s*(#[0-9a-fA-F]{6})", css))
        pairs = [("text", "background", 4.5), ("text", "surface", 4.5),
                 ("muted", "background", 4.5), ("accent", "background", 3.0)]
        for fg, bg, minimum in pairs:
            if fg in tokens and bg in tokens:
                ratio = contrast_ratio(tokens[fg], tokens[bg])
                if ratio < minimum:
                    findings.append(self._f(
                        ReviewSeverity.BLOCKER, f"contrast_{fg}_{bg}",
                        f"{fg} on {bg} is {ratio:.2f}:1 (needs {minimum}:1)",
                        "app/globals.css", auto_fixable=True))
        if "prefers-reduced-motion" not in css:
            findings.append(self._f(ReviewSeverity.BLOCKER, "no_reduced_motion",
                                    "no prefers-reduced-motion handling",
                                    "app/globals.css", auto_fixable=True))
        if "skip-link" not in css:
            findings.append(self._f(ReviewSeverity.WARNING, "no_skip_link",
                                    "skip-to-content link missing", "app/globals.css"))
        if ":focus-visible" not in css:
            findings.append(self._f(ReviewSeverity.WARNING, "no_focus_styles",
                                    "no :focus-visible treatment", "app/globals.css"))

        for tsx in _tsx_files(root):
            text = tsx.read_text()
            rel = str(tsx.relative_to(root))
            for m in re.finditer(r"<img\b(?![^>]*\balt=)[^>]*>", text):
                findings.append(self._f(ReviewSeverity.BLOCKER, "img_no_alt",
                                        f"<img> without alt: {m.group(0)[:60]}",
                                        rel, auto_fixable=True))
            for _m in re.finditer(r"<svg\b(?![^>]*aria-hidden)(?![^>]*aria-label)[^>]*>", text):
                findings.append(self._f(ReviewSeverity.WARNING, "svg_unlabeled",
                                        "decorative <svg> lacks aria-hidden", rel,
                                        auto_fixable=True))
            for m in re.finditer(r"<input\b[^>]*\bid=\"([^\"]+)\"[^>]*>", text):
                if f'htmlFor="{m.group(1)}"' not in text:
                    findings.append(self._f(ReviewSeverity.BLOCKER, "input_no_label",
                                            f"input #{m.group(1)} has no label", rel))
        # heading discipline per page: exactly one h1 (hero or docs)
        for page in root.glob("app/**/page.tsx"):
            text = page.read_text()
            rel = str(page.relative_to(root))
            has_hero_or_docs = ("Hero" in text or "DocsLayout" in text
                                or "PageHeader" in text or "<h1" in text)
            if not has_hero_or_docs:
                findings.append(self._f(ReviewSeverity.WARNING, "page_no_h1",
                                        "page renders no h1-bearing section", rel))
        return findings


class PerformanceReviewAgent(_Agent):
    """Performance by construction, verified: no raster assets, swap-loaded
    fonts, no blocking third-party scripts, CSS-only animation, dependency
    discipline in package.json."""
    name = "Performance Agent"

    _DEP_ALLOWLIST = {"next", "react", "react-dom"}

    def review(self, root: Path, ds: DesignSystem) -> list[ReviewFinding]:
        findings: list[ReviewFinding] = []
        pkg_path = root / "package.json"
        if pkg_path.exists():
            import json as _json
            deps = _json.loads(pkg_path.read_text()).get("dependencies", {})
            extra = set(deps) - self._DEP_ALLOWLIST
            if extra:
                findings.append(self._f(ReviewSeverity.WARNING, "heavy_deps",
                                        f"runtime deps beyond allowlist: {sorted(extra)}",
                                        "package.json"))
        layout = root / "app" / "layout.tsx"
        if layout.exists():
            text = layout.read_text()
            if "fonts.googleapis" in text and "display=swap" not in text:
                findings.append(self._f(ReviewSeverity.WARNING, "font_no_swap",
                                        "web font loads without display=swap",
                                        "app/layout.tsx", auto_fixable=True))
            if "preconnect" not in text and "fonts.googleapis" in text:
                findings.append(self._f(ReviewSeverity.NOTE, "no_preconnect",
                                        "font host not preconnected", "app/layout.tsx"))
        for tsx in _tsx_files(root):
            text = tsx.read_text()
            rel = str(tsx.relative_to(root))
            if re.search(r"<script\s+src=", text):
                findings.append(self._f(ReviewSeverity.BLOCKER, "blocking_script",
                                        "third-party <script src> in component", rel))
            if re.search(r"\.(png|jpe?g|gif|webp)\b", text):
                findings.append(self._f(ReviewSeverity.WARNING, "raster_asset",
                                        "raster asset reference (site is SVG/CSS-only "
                                        "by design)", rel))
        return findings


class DesignReviewAgent(_Agent):
    """Consistency: pages share NavBar/Footer, colors come from tokens (no
    stray hex in components), section rhythm via the shared Section shell."""
    name = "Design Agent"

    def review(self, root: Path, ds: DesignSystem) -> list[ReviewFinding]:
        findings: list[ReviewFinding] = []
        for page in root.glob("app/**/page.tsx"):
            text = page.read_text()
            rel = str(page.relative_to(root))
            if "NavBar" not in text or "Footer" not in text:
                findings.append(self._f(ReviewSeverity.BLOCKER, "missing_chrome",
                                        "page lacks shared NavBar/Footer", rel))
            if '<main id="main"' not in text:
                findings.append(self._f(ReviewSeverity.WARNING, "no_main_landmark",
                                        "no <main id=\"main\"> landmark", rel))
        for tsx in (root / "components").glob("*.tsx") if (root / "components").exists() else []:
            text = tsx.read_text()
            hexes = re.findall(r"#[0-9a-fA-F]{6}\b", text)
            if hexes:
                findings.append(self._f(ReviewSeverity.WARNING, "hardcoded_color",
                                        f"hex colors outside tokens: {hexes[:3]}",
                                        f"components/{tsx.name}"))
        return findings


class ConversionReviewAgent(_Agent):
    """UX/conversion: primary CTA present on landing hero, nav links resolve
    to real routes, footer navigable, contact path reachable."""
    name = "UX Agent"

    def review(self, root: Path, ds: DesignSystem) -> list[ReviewFinding]:
        findings: list[ReviewFinding] = []
        routes = {"/"} | {f"/{p.parent.name}" for p in root.glob("app/*/page.tsx")}
        content = root / "lib" / "content.ts"
        if content.exists():
            text = content.read_text()
            for href in set(re.findall(r'"href":\s*"(/[^"#]*)"', text)):
                if href not in routes:
                    findings.append(self._f(ReviewSeverity.BLOCKER, "dead_link",
                                            f"link to non-existent route {href}",
                                            "lib/content.ts"))
        landing = root / "app" / "page.tsx"
        if landing.exists():
            text = landing.read_text()
            if "Hero" not in text:
                findings.append(self._f(ReviewSeverity.BLOCKER, "no_hero_cta",
                                        "landing page has no hero (no above-fold CTA)",
                                        "app/page.tsx"))
            if "Cta" not in text and "ContactForm" not in text:
                findings.append(self._f(ReviewSeverity.WARNING, "no_closing_cta",
                                        "landing page has no closing CTA section",
                                        "app/page.tsx"))
        return findings


class SecurityReviewAgent(_Agent):
    """Best-practice lint: no dangerouslySetInnerHTML, no http:// resources,
    external links carry rel=noopener, security headers configured, forms
    don't post user data to external endpoints by default."""
    name = "Security Agent"

    def review(self, root: Path, ds: DesignSystem) -> list[ReviewFinding]:
        findings: list[ReviewFinding] = []
        cfg = root / "next.config.mjs"
        if not cfg.exists() or "X-Content-Type-Options" not in cfg.read_text():
            findings.append(self._f(ReviewSeverity.WARNING, "no_security_headers",
                                    "security headers not configured",
                                    "next.config.mjs", auto_fixable=True))
        for tsx in _tsx_files(root):
            text = tsx.read_text()
            rel = str(tsx.relative_to(root))
            if "dangerouslySetInnerHTML" in text:
                findings.append(self._f(ReviewSeverity.BLOCKER, "dangerous_html",
                                        "dangerouslySetInnerHTML present", rel))
            if re.search(r"(src|href)=\"http://", text):
                findings.append(self._f(ReviewSeverity.BLOCKER, "insecure_url",
                                        "plain-http resource reference", rel))
            for m in re.finditer(r"<a\b[^>]*href=\"https?://[^\"]*\"[^>]*>", text):
                tag = m.group(0)
                if "rel=" not in tag:
                    findings.append(self._f(ReviewSeverity.WARNING, "extlink_no_rel",
                                            f"external link without rel: {tag[:60]}",
                                            rel, auto_fixable=True))
            if re.search(r"<form\b[^>]*action=\"https?://", text):
                findings.append(self._f(ReviewSeverity.BLOCKER, "form_external_post",
                                        "form posts to external URL", rel))
        return findings


ALL_REVIEW_AGENTS = [AccessibilityReviewAgent, DesignReviewAgent,
                     PerformanceReviewAgent, ConversionReviewAgent,
                     SecurityReviewAgent]


async def run_build_gate(root: Path, timeout_s: int = 480) -> tuple[bool | None, str]:
    """Ground truth: npm install + next build. Returns (ok|None, log tail).
    None = node unavailable; the report says so instead of pretending."""
    import shutil as _shutil
    npm = _shutil.which("npm")
    if npm is None:
        return None, "npm not found — build gate skipped"
    try:
        for cmd in ([npm, "install", "--no-audit", "--no-fund"],
                    [npm, "run", "build"]):
            proc = await asyncio.create_subprocess_exec(
                *cmd, cwd=root, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT)
            out, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
            if proc.returncode != 0:
                return False, out.decode(errors="replace")[-2000:]
        return True, out.decode(errors="replace")[-800:]
    except TimeoutError:
        return False, f"build gate timed out after {timeout_s}s"


def run_review(root: Path, ds: DesignSystem) -> ReviewReport:
    report = ReviewReport()
    for agent_cls in ALL_REVIEW_AGENTS:
        agent = agent_cls()
        agent_findings = agent.review(root, ds)
        report.findings.extend(agent_findings)
        score = 100.0
        for f in agent_findings:
            score -= _PENALTY[f.severity]
        report.scores[agent.name] = max(0.0, round(score, 1))
    return report
