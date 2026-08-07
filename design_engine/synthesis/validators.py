"""Deterministic design validators — the gates behind the synthesis LLM.

  contrast_ratio / fix_palette_contrast   WCAG AA enforced by math: text/bg
      pairs below 4.5:1 have their lightness walked until they pass, so an
      inaccessible palette cannot leave this module no matter what the LLM
      proposed.

  novelty_check   the anti-copying gate made executable: the synthesized
      palette must not reproduce any single analyzed site's palette (>=60%
      of roles within a tight RGB distance of one source = too close), and
      inspirations must span >= 2 distinct sites when the corpus offers
      them. Synthesis means drawing from MANY sources; this proves it.
"""

from __future__ import annotations

from ..models import Palette

_AA_NORMAL = 4.5
_AA_LARGE = 3.0


def _rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    try:
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except ValueError:
        return (128, 128, 128)


def _hex(r: int, g: int, b: int) -> str:
    clamp = lambda v: max(0, min(255, int(v)))  # noqa: E731
    return f"#{clamp(r):02x}{clamp(g):02x}{clamp(b):02x}"


def _luminance(hex_color: str) -> float:
    r, g, b = (c / 255.0 for c in _rgb(hex_color))
    lin = lambda c: c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4  # noqa: E731
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def contrast_ratio(a: str, b: str) -> float:
    la, lb = _luminance(a), _luminance(b)
    lighter, darker = max(la, lb), min(la, lb)
    return (lighter + 0.05) / (darker + 0.05)


def _nudge(color: str, lighter: bool, step: int = 12) -> str:
    r, g, b = _rgb(color)
    delta = step if lighter else -step
    return _hex(r + delta, g + delta, b + delta)


def _force_contrast(fg: str, bg: str, minimum: float, max_steps: int = 30) -> str:
    """Walk fg's lightness away from bg until the pair passes. Convergence is
    guaranteed: pure white/black against anything exceeds AA thresholds."""
    color = fg
    lighter = _luminance(bg) < 0.5  # dark bg → lighten text, and vice versa
    for _ in range(max_steps):
        if contrast_ratio(color, bg) >= minimum:
            return color
        color = _nudge(color, lighter)
    return "#ffffff" if lighter else "#000000"


def fix_palette_contrast(p: Palette) -> tuple[Palette, list[str]]:
    """Returns (AA-guaranteed palette, list of adjustments made)."""
    fixes: list[str] = []
    text = _force_contrast(p.text, p.background, _AA_NORMAL)
    if text != p.text:
        fixes.append(f"text {p.text}→{text} vs background")
    muted = _force_contrast(p.muted, p.background, _AA_NORMAL)
    if muted != p.muted:
        fixes.append(f"muted {p.muted}→{muted} vs background")
    accent = _force_contrast(p.accent, p.background, _AA_LARGE)  # large/UI elements
    if accent != p.accent:
        fixes.append(f"accent {p.accent}→{accent} vs background")
    text_s = _force_contrast(text, p.surface, _AA_NORMAL)
    if text_s != text:
        fixes.append(f"text {text}→{text_s} vs surface")
        text = text_s
    return Palette(background=p.background, surface=p.surface,
                   text=text, muted=muted, accent=accent), fixes


def _close(a: str, b: str, tolerance: int = 24) -> bool:
    ra, ga, ba = _rgb(a)
    rb, gb, bb = _rgb(b)
    return abs(ra - rb) + abs(ga - gb) + abs(ba - bb) <= tolerance


def novelty_check(palette: Palette, source_palettes: dict[str, list[str]],
                  inspiration_sites: list[str]) -> tuple[bool, str]:
    """(ok, note). Fails when the synthesized palette collapses onto one
    analyzed site, or when inspiration provenance names fewer than two
    sites despite a multi-site corpus."""
    roles = [palette.background, palette.surface, palette.text,
             palette.muted, palette.accent]
    for url, source in source_palettes.items():
        if not source:
            continue
        matched = sum(1 for role in roles
                      if any(_close(role, s) for s in source[:8]))
        if matched >= 3:  # 3 of 5 roles from ONE site = derivative
            return False, f"palette tracks {url} too closely ({matched}/5 roles)"
    distinct = len(set(inspiration_sites))
    if len(source_palettes) >= 2 and distinct < 2:
        return False, f"synthesis cites only {distinct} inspiration site(s)"
    return True, (f"novel: no single-source palette overlap; "
                  f"{distinct} inspiration sites cited")
