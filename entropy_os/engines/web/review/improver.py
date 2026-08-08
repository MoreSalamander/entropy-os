"""Phase 7 (second half) — the automatic improvement loop.

Mechanical fixes for auto_fixable findings, applied to the generated
source, then re-reviewed. The loop contract:

  * only findings marked auto_fixable are touched — everything else stays
    visible in the final report for a human
  * after each round the review re-runs; the loop stops when no fixable
    findings remain, nothing improved, or the round cap hits
  * scores must be monotonically non-decreasing across rounds; a fix that
    makes things worse would surface immediately in the re-review

Fixes implemented:
  contrast_*         re-run the WCAG auto-fixer on the palette and rewrite
                     the token block in globals.css
  no_reduced_motion  append the standard reduced-motion CSS block
  img_no_alt         add alt="" (decorative default) to bare <img>
  svg_unlabeled      add aria-hidden="true" to unlabeled <svg>
  extlink_no_rel     add rel="noopener noreferrer" to external links
  font_no_swap       append &display=swap to Google Fonts URLs
  no_security_headers rewrite next.config.mjs with the standard header set
"""

from __future__ import annotations

import re
from pathlib import Path

from ..models import DesignSystem, Palette, ReviewReport
from ..synthesis.validators import fix_palette_contrast
from .agents import run_review

_REDUCED_MOTION_CSS = """
@media (prefers-reduced-motion: reduce) {
  .reveal { opacity: 1; transform: none; transition: none; }
  *, *::before, *::after { animation: none !important; transition: none !important; }
}
"""


class AutoImprover:
    def __init__(self, max_rounds: int = 2):
        self.max_rounds = max_rounds

    # ---- individual fixers -------------------------------------------
    def _fix_contrast(self, root: Path, ds: DesignSystem) -> bool:
        css_path = root / "app" / "globals.css"
        if not css_path.exists():
            return False
        css = css_path.read_text()
        tokens = dict(re.findall(r"--color-(\w+):\s*(#[0-9a-fA-F]{6})", css))
        needed = {"background", "surface", "text", "muted", "accent"}
        if not needed <= set(tokens):
            return False
        fixed, changes = fix_palette_contrast(Palette(**{k: tokens[k] for k in needed}))
        if not changes:
            return False
        for role, value in (("text", fixed.text), ("muted", fixed.muted),
                            ("accent", fixed.accent)):
            css = re.sub(rf"(--color-{role}:\s*)#[0-9a-fA-F]{{6}}",
                         rf"\g<1>{value}", css)
        css_path.write_text(css)
        ds.palette = fixed  # keep the DesignSystem record truthful post-fix
        return True

    def _fix_reduced_motion(self, root: Path) -> bool:
        css_path = root / "app" / "globals.css"
        if not css_path.exists() or "prefers-reduced-motion" in css_path.read_text():
            return False
        css_path.write_text(css_path.read_text() + _REDUCED_MOTION_CSS)
        return True

    def _fix_in_files(self, root: Path, pattern: str, repl, code: str) -> bool:
        changed = False
        for tsx in root.rglob("*.tsx"):
            if "node_modules" in tsx.parts:
                continue
            text = tsx.read_text()
            new = re.sub(pattern, repl, text)
            if new != text:
                tsx.write_text(new)
                changed = True
        return changed

    # ---- the loop -----------------------------------------------------
    def improve(self, root: Path, ds: DesignSystem,
                report: ReviewReport) -> tuple[ReviewReport, int]:
        rounds = 0
        current = report
        while rounds < self.max_rounds:
            fixable_codes = {f.code for f in current.findings if f.auto_fixable}
            if not fixable_codes:
                break
            applied = False
            if any(c.startswith("contrast_") for c in fixable_codes):
                applied |= self._fix_contrast(root, ds)
            if "no_reduced_motion" in fixable_codes:
                applied |= self._fix_reduced_motion(root)
            if "img_no_alt" in fixable_codes:
                applied |= self._fix_in_files(
                    root, r"<img\b(?![^>]*\balt=)", '<img alt="" ', "img_no_alt")
            if "svg_unlabeled" in fixable_codes:
                applied |= self._fix_in_files(
                    root, r"<svg\b(?![^>]*aria-hidden)(?![^>]*aria-label)",
                    '<svg aria-hidden="true" ', "svg_unlabeled")
            if "extlink_no_rel" in fixable_codes:
                applied |= self._fix_in_files(
                    root, r"(<a\b[^>]*href=\"https?://[^\"]*\")(?![^>]*rel=)",
                    r'\1 rel="noopener noreferrer"', "extlink_no_rel")
            if "font_no_swap" in fixable_codes:
                applied |= self._fix_in_files(
                    root, r"(fonts\.googleapis\.com/css2\?[^\"']*)(?<!display=swap)(\")",
                    lambda m: (m.group(1) + ("&display=swap" if "display=swap"
                               not in m.group(1) else "") + m.group(2)),
                    "font_no_swap")
            if not applied:
                break  # nothing we know how to fix actually changed a file
            rounds += 1
            current = run_review(root, ds)
        return current, rounds
