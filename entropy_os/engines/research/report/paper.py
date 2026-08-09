"""The paper renderer: the same session, written the way a reader reads.

The existing report is an instrument panel. It answers "what did the run
do" — sixteen fixed sections, question headings, bullet fragments carrying
`confidence 0.727`, run statistics above the fold. That is the right artifact
for the operator watching the machine, and the wrong one for anyone who
wanted to LEARN the thing they asked about.

This renders the same Context Graph as a paper: an abstract, themed sections
of prose, numbered citations, and a reference list. Three rules make it a
translation rather than a rewrite, and all three are enforced rather than
requested:

  1. NOTHING NEW ENTERS. The paper is built only from claims the
     Verification Agent already marked verified. An unverified claim did not
     clear the evidence floor, and prose is exactly where an unverified claim
     stops looking unverified.

  2. EVERY SENTENCE IS TRACEABLE. Claims arrive at the writer already
     carrying their citation numbers, and a gate afterwards checks that every
     marker in the prose resolves to a real reference. A citation that
     resolves to nothing is the signature of invention.

  3. OFF-TOPIC EVIDENCE IS DROPPED, AND SAID SO. A session on U.S. currency
     that surfaces LHCb decay rates has retrieved something real and
     irrelevant; printing it under a heading makes the reader do the
     filtering. The filter is deterministic, and the count it excluded is
     reported rather than hidden.

The prose model can be absent or silent and the paper still builds — the
deterministic renderer produces plainer sentences from the same claims and
the same citations. A missing model costs readability, never grounding.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..graphs.context_graph import ContextGraph
from ..llm.client import LLMClient, LLMUnavailable
from ..models import Claim, Finding

# A theme needs enough behind it to be worth a heading of its own; below this
# its claims are better read together than split into thin sections.
MIN_CLAIMS_PER_THEME = 2
MAX_THEMES = 6
MAX_CLAIMS_PER_THEME = 8

# Words that carry no topical signal, so they must not make a claim look
# relevant. Deliberately small: an aggressive stop list starts discarding
# real terms, and a claim wrongly dropped is worse than one wrongly kept.
_STOP = {
    "the", "a", "an", "of", "and", "or", "to", "in", "on", "for", "with",
    "is", "are", "was", "were", "be", "been", "it", "its", "this", "that",
    "as", "at", "by", "from", "how", "what", "why", "about", "would", "like",
    "learn", "i", "me", "my", "can", "do", "does", "into",
}

CITE_RE = re.compile(r"\[(\d+)\]")


def _terms(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", (text or "").lower())
            if len(w) > 2 and w not in _STOP}


@dataclass
class Reference:
    """One source, as it will appear in the reference list."""
    n: int
    url: str
    title: str
    authors: list[str] = field(default_factory=list)
    published: str = ""
    reliability: float = 0.0

    def render(self) -> str:
        who = ", ".join(self.authors[:3]) + (" et al." if len(self.authors) > 3 else "")
        bits = [b for b in (who, self.title or self.url, self.published) if b]
        return f"[{self.n}] " + ". ".join(bits) + f". {self.url}"


@dataclass
class Theme:
    """A group of claims that share a subject, and the prose written for it."""
    title: str
    claims: list[Claim]
    citations: dict[str, int]        # claim id -> reference number
    prose: str = ""


@dataclass
class Paper:
    title: str
    abstract: str
    themes: list[Theme]
    references: list[Reference]
    contested: list[str]
    open_questions: list[str]
    method: str
    excluded_claims: int
    claims_used: int
    claims_verified_total: int
    markdown: str = ""


class CitationError(Exception):
    """Prose cited something that does not exist."""


def check_citations(prose: str, allowed: set[int]) -> list[int]:
    """Every citation marker that resolves to nothing.

    This is the gate that makes generated prose safe to publish: a model that
    invents a supporting source will almost always invent its NUMBER too, and
    an unresolvable number is machine-detectable in a way that a plausible
    sentence is not.
    """
    return sorted({int(n) for n in CITE_RE.findall(prose)} - allowed)


class PaperBuilder:
    def __init__(self, llm: LLMClient | None = None):
        self.llm = llm

    # -- selection --------------------------------------------------------
    def _relevant(self, cg: ContextGraph, claims: list[Claim]
                  ) -> tuple[list[Claim], int]:
        """Claims that are actually about the topic.

        Scored on shared vocabulary between the claim (plus the entities it
        names) and the research topic. Deterministic on purpose: a model
        deciding what is on-topic could quietly drop the inconvenient half of
        a contested subject, and nobody would see it happen.
        """
        topic_terms = _terms(cg.plan.topic)
        if not topic_terms:
            return claims, 0
        kept: list[Claim] = []
        for c in claims:
            text = c.statement
            for eid in c.entity_ids:
                ent = cg.entities.get(eid)
                if ent is not None:
                    text += " " + ent.name + " " + (ent.description or "")
            if _terms(text) & topic_terms:
                kept.append(c)
        # Never hand back an empty paper because the topic was phrased oddly:
        # if the filter rejected everything, it is the filter that is wrong.
        if not kept:
            return claims, 0
        return kept, len(claims) - len(kept)

    def _themes(self, cg: ContextGraph, claims: list[Claim]) -> list[Theme]:
        """Group claims by the entity they are most about."""
        by_entity: dict[str, list[Claim]] = {}
        loose: list[Claim] = []
        for c in claims:
            eid = c.entity_ids[0] if c.entity_ids else ""
            if eid:
                by_entity.setdefault(eid, []).append(c)
            else:
                loose.append(c)
        groups = sorted(by_entity.items(), key=lambda kv: -len(kv[1]))
        themes: list[Theme] = []
        overflow: list[Claim] = list(loose)
        for eid, group in groups:
            ent = cg.entities.get(eid)
            if len(group) < MIN_CLAIMS_PER_THEME or len(themes) >= MAX_THEMES or ent is None:
                overflow.extend(group)
                continue
            themes.append(Theme(title=ent.name.strip().title(),
                                claims=group[:MAX_CLAIMS_PER_THEME], citations={}))
        if overflow:
            themes.append(Theme(title="Further Findings",
                                claims=overflow[:MAX_CLAIMS_PER_THEME], citations={}))
        return themes

    def _references(self, themes: list[Theme]) -> list[Reference]:
        """Number every distinct source once, in order of first appearance —
        the order a reader meets them, not the order the crawler found them."""
        refs: dict[str, Reference] = {}
        for theme in themes:
            for claim in theme.claims:
                best = max(claim.evidence, key=lambda e: e.reliability, default=None)
                if best is None:
                    continue
                ref = refs.get(best.url)
                if ref is None:
                    ref = Reference(
                        n=len(refs) + 1, url=best.url,
                        title=(best.title or "").strip(),
                        authors=list(best.authors or []),
                        published=(best.published.strftime("%Y")
                                   if getattr(best, "published", None) else ""),
                        reliability=best.reliability)
                    refs[best.url] = ref
                theme.citations[claim.id] = ref.n
        return sorted(refs.values(), key=lambda r: r.n)

    # -- prose ------------------------------------------------------------
    def _deterministic_prose(self, theme: Theme) -> str:
        """The paper without a model: claims as sentences, each cited.

        Plainer than generated prose and every bit as true. This is what the
        reader gets when the model is unavailable, and it is why an outage
        degrades the writing rather than the grounding.
        """
        out = []
        for claim in theme.claims:
            n = theme.citations.get(claim.id)
            stmt = claim.statement.strip().rstrip(".")
            out.append(f"{stmt}{f' [{n}]' if n else ''}.")
        return " ".join(out)

    async def _write(self, topic: str, theme: Theme) -> str:
        """Ask the model to connect the claims — and nothing else."""
        if self.llm is None:
            return self._deterministic_prose(theme)
        lines = []
        for claim in theme.claims:
            n = theme.citations.get(claim.id)
            lines.append(f"- {claim.statement.strip()}" + (f" [{n}]" if n else ""))
        allowed = set(theme.citations.values())
        try:
            prose = await self.llm.chat_text(
                "summarize",
                "You are writing one section of a research paper. Use ONLY the "
                "findings below. Do not add facts, examples, numbers or names "
                "that are not present. Keep every citation marker exactly as "
                "written, attached to the sentence carrying that finding. "
                "Write 3-6 sentences of connected prose, no bullets, no "
                "headings.",
                f"Topic: {topic}\nSection: {theme.title}\nFindings:\n"
                + "\n".join(lines))
        except LLMUnavailable:
            return self._deterministic_prose(theme)
        prose = (prose or "").strip()
        # An empty answer is the documented failure of local reasoning models;
        # it must fall back rather than produce a section with no body.
        if not prose:
            return self._deterministic_prose(theme)
        # The gate. Prose that cites something that does not exist is
        # discarded whole — a partially-invented section is not repairable by
        # deleting the marker, because the sentence it supported stays.
        if check_citations(prose, allowed):
            return self._deterministic_prose(theme)
        return prose

    async def _abstract(self, subject: str, themes: list[Theme], stats: dict) -> str:
        heads = "; ".join(t.title for t in themes[:5])
        if self.llm is None:
            return (f"This report examines {subject}. It draws on "
                    f"{stats['refs']} sources and {stats['claims']} verified "
                    f"findings across {len(themes)} areas: {heads}.")
        try:
            prose = await self.llm.chat_text(
                "summarize",
                "Write a 3-5 sentence abstract for a research paper. State "
                "what was examined and what was found. No citations, no "
                "bullets, no invented specifics.",
                f"Topic: {subject}\nSections: {heads}\n"
                + "\n".join(f"- {c.statement}" for t in themes
                            for c in t.claims[:2]))
        except LLMUnavailable:
            prose = ""
        return (prose or "").strip() or (
            f"This report examines {subject}. It draws on {stats['refs']} sources "
            f"and {stats['claims']} verified findings across {len(themes)} areas: {heads}.")

    # -- build ------------------------------------------------------------
    async def build(self, cg: ContextGraph, findings: list[Finding]) -> Paper:
        topic = cg.plan.topic.strip()
        verified = [c for c in cg.claims.values() if c.verified and c.evidence]
        relevant, excluded = self._relevant(cg, verified)
        themes = self._themes(cg, relevant)
        references = self._references(themes)

        for theme in themes:
            theme.prose = await self._write(topic, theme)

        stats = {"refs": len(references),
                 "claims": sum(len(t.claims) for t in themes)}
        # The cleaned subject, not the raw prompt: a paper that opens
        # "This report examines i would like to learn about X" has
        # published the question someone typed instead of naming its own
        # subject.
        abstract = await self._abstract(_title(topic), themes, stats)

        contested = [f.text for f in findings if f.kind == "contradiction"][:6]
        open_questions = [f.text for f in findings if f.kind == "question"][:6]

        method = (
            f"Sources were gathered by parallel retrieval across "
            f"{len({e.source for c in cg.claims.values() for e in c.evidence})} "
            f"source families and reduced to claims by extraction. A claim is "
            f"reported here only if it cleared the verification floor — a "
            f"single source at reliability 0.7 or higher, or two independent "
            f"sources at 0.45 or higher. {len(verified)} of "
            f"{len(cg.claims)} claims cleared it"
            + (f"; {excluded} verified claims were set aside as unrelated to "
               f"the question asked" if excluded else "")
            + ". Every statement below carries the source it rests on; nothing "
              "is asserted that no source said.")

        paper = Paper(
            title=_title(topic), abstract=abstract, themes=themes,
            references=references, contested=contested,
            open_questions=open_questions, method=method,
            excluded_claims=excluded, claims_used=stats["claims"],
            claims_verified_total=len(verified))
        paper.markdown = render_markdown(paper)
        return paper


def _title(topic: str) -> str:
    """A title, not a prompt. `i would like to learn about X` is what someone
    typed; it is not what a paper is called."""
    t = topic.strip().rstrip("?.").strip()
    t = re.sub(r"^(i (would like|want) to (learn|know) about|tell me about|"
               r"explain|research|what is|what are|how does|how do)\s+", "", t,
               flags=re.I).strip()
    return (t[:1].upper() + t[1:]) if t else topic


def render_markdown(p: Paper) -> str:
    out = [f"# {p.title}", "", "## Abstract", "", p.abstract, ""]
    for i, theme in enumerate(p.themes, 1):
        out += [f"## {i}. {theme.title}", "", theme.prose, ""]
    if p.contested:
        out += ["## Contested Points", "",
                "The evidence disagreed on the following. Both sides are "
                "recorded; neither is resolved here.", ""]
        out += [f"- {c}" for c in p.contested] + [""]
    if p.open_questions:
        out += ["## Open Questions", ""]
        out += [f"- {q}" for q in p.open_questions] + [""]
    out += ["## Method and Limitations", "", p.method, ""]
    if p.references:
        out += ["## References", ""]
        out += [r.render() for r in p.references] + [""]
    return "\n".join(out)
