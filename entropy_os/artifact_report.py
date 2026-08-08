"""Presenting a composed run's research report the way this house presents
reports: as a document, with its grounding visible.

The convention is `_report_document_html` in app.py — kicker, title, a meta
line, and every claim shown beside the source that grounds it, so the
verification model is on the page rather than only in the gate ledger. A
research report from one-engine carries the same grounding in a different
shape: an Evidence Table of source / title+link / date / authors / confidence,
plus Source References and Confidence Scores.

So the job here is not to invent a second presentation. It is to render that
markdown faithfully — tables as tables, links as links — into the same document
shell, because dumping it into a <pre> destroys precisely the part that makes
it a verified report rather than an essay.

Deliberately dependency-free: this renders the subset the reports actually use
(headings, tables, links, emphasis, code, lists, rules) rather than pulling a
markdown library into the image for one page.
"""

from __future__ import annotations

import html
import re

_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_BOLD = re.compile(r"\*\*([^*]+)\*\*")
_CODE = re.compile(r"`([^`]+)`")
# Italics only at word boundaries. These reports are full of identifiers like
# `session_86d80f666e84` and `tasks_spawned=112`; a naive `_..._` rule eats the
# middle of every one of them.
_ITAL = re.compile(r"(?<!\w)_([^\n]+?)_(?!\w)")


def _inline(text: str) -> str:
    """Escape first, then re-introduce only the markup we chose to support.

    Order matters: escaping after link substitution would mangle the href, and
    escaping never would put report content into the DOM unfiltered.
    """
    out = html.escape(text)
    out = _CODE.sub(r"<code>\1</code>", out)
    out = _BOLD.sub(r"<strong>\1</strong>", out)
    out = _ITAL.sub(r"<em>\1</em>", out)

    def link(m: re.Match[str]) -> str:
        label, href = m.group(1), m.group(2)
        # Only http(s) becomes a link. A report is untrusted-ish content; a
        # javascript: or data: href in a rendered document is a scripting hole.
        if not href.lower().startswith(("http://", "https://")):
            return label
        return (f'<a href="{href}" target="_blank" rel="noopener noreferrer">'
                f"{label}</a>")

    return _LINK.sub(link, out)


def _table(rows: list[str]) -> str:
    """A markdown pipe table. The Evidence Table is the grounding, so this is
    the one block that most needs to survive rendering intact."""
    def cells(line: str) -> list[str]:
        return [c.strip() for c in line.strip().strip("|").split("|")]

    head, body = cells(rows[0]), [cells(r) for r in rows[2:]]
    ths = "".join(f"<th>{_inline(c)}</th>" for c in head)
    trs = "".join(
        "<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in r) + "</tr>"
        for r in body)
    return f"<table><thead><tr>{ths}</tr></thead><tbody>{trs}</tbody></table>"


def markdown_to_html(md: str) -> str:
    """Render the subset these reports use. Unknown syntax degrades to text."""
    out: list[str] = []
    lines = md.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            i += 1
            continue

        if stripped.startswith("#"):
            level = len(stripped) - len(stripped.lstrip("#"))
            out.append(f"<h{min(level, 4)}>"
                       f"{_inline(stripped[level:].strip())}</h{min(level, 4)}>")
            i += 1
            continue

        # A pipe table needs its separator row to be a table at all.
        if (stripped.startswith("|") and i + 1 < len(lines)
                and set(lines[i + 1].strip()) <= set("|-: ")):
            block = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                block.append(lines[i])
                i += 1
            out.append(_table(block))
            continue

        if set(stripped) <= {"-", "_", "*"} and len(stripped) >= 3:
            out.append("<hr>")
            i += 1
            continue

        if re.match(r"^([-*+]|\d+\.)\s+", stripped):
            ordered = bool(re.match(r"^\d+\.\s+", stripped))
            items = []
            while i < len(lines) and re.match(r"^([-*+]|\d+\.)\s+",
                                              lines[i].strip()):
                items.append(re.sub(r"^([-*+]|\d+\.)\s+", "",
                                    lines[i].strip()))
                i += 1
            tag = "ol" if ordered else "ul"
            out.append(f"<{tag}>"
                       + "".join(f"<li>{_inline(it)}</li>" for it in items)
                       + f"</{tag}>")
            continue

        para = []
        while i < len(lines) and lines[i].strip() and not lines[i].strip().startswith(
                ("#", "|", "-", "*")):
            para.append(lines[i].strip())
            i += 1
        if para:
            out.append(f"<p>{_inline(' '.join(para))}</p>")
        else:
            out.append(f"<p>{_inline(stripped)}</p>")
            i += 1
    return "".join(out)


# Additions to the house report CSS for blocks the Veritas reports never had.
EXTRA_CSS = """
  table { width:100%; border-collapse:collapse; margin:18px 0; font-family:var(--mono);
          font-size:11.5px; display:block; overflow-x:auto; }
  th, td { border:1px solid var(--line); padding:6px 8px; text-align:left; vertical-align:top; }
  th { color:var(--cyan); font-weight:600; white-space:nowrap; }
  td a { color:var(--quote); }
  h2 { font-size:22px; margin:34px 0 8px; letter-spacing:-.2px; }
  h3 { font-size:17px; margin:24px 0 6px; color:var(--dim); }
  ul, ol { padding-left:22px; } li { margin:4px 0; }
  code { font-family:var(--mono); font-size:12px; color:var(--quote); }
  hr { border:0; border-top:1px solid var(--line); margin:28px 0; }
"""


def document_html(css: str, *, kicker: str, title: str, meta: str,
                  badge: str, body_md: str, footer: str) -> str:
    """The house document shell, around a rendered markdown body."""
    e = html.escape
    return (
        '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{e(title)}</title><style>{css}{EXTRA_CSS}</style></head>"
        '<body><div class="wrap">'
        f'<div class="kicker">{e(kicker)}</div>'
        f"<h1>{e(title)}</h1>"
        f'<div class="meta">{e(meta)}</div>'
        f'<div class="verified">{e(badge)}</div>'
        f"{markdown_to_html(body_md)}"
        f"<footer>{footer}</footer>"
        "</div></body></html>"
    )
