"""Final Research Output — every section the spec names, none silently dropped.

Sections (fixed order, always all present):
  Executive Summary · What Changed Recently? · What Is the Consensus? ·
  What Remains Uncertain? · What Connections Were Discovered? ·
  Research Map · Major Entities · Key Findings · Evidence Table · Timeline ·
  Arguments For/Against · Unknowns · Future Predictions ·
  Related Discoveries · Confidence Scores · Source References

Honesty rules:
  * every section carries item_count = the number of REAL content items
    rendered (content fidelity is countable, not marker-greppable)
  * a section with nothing to say says "No X was established in this
    session" — it never pads, and Future Predictions is explicitly labeled
    as trend extrapolation with confidence, never presented as fact
  * only the Executive Summary uses LLM prose, and it is generated FROM the
    already-built evidence-backed sections
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from ..graphs.context_graph import ContextGraph
from ..llm.client import LLMClient, LLMUnavailable
from ..models import Finding, Polarity, ReportSection, ResearchReport, TimelineEvent


def _empty(title: str, reason: str) -> ReportSection:
    return ReportSection(title=title, body_md=f"_{reason}_", item_count=0)


class ReportBuilder:
    def __init__(self, llm: LLMClient):
        self.llm = llm

    # ------------------------------------------------------------------ #
    async def build(self, cg: ContextGraph, findings: list[Finding],
                    run_stats: dict, source_table: list[dict],
                    consolidation: dict, datahub_status: str) -> ResearchReport:
        by_kind: dict[str, list[Finding]] = defaultdict(list)
        for f in findings:
            by_kind[f.kind].append(f)

        sections = [
            await self._exec_summary(cg, by_kind),
            self._what_changed(by_kind),
            self._consensus(cg),
            self._uncertain(cg, by_kind),
            self._connections(by_kind),
            self._research_map(cg),
            self._major_entities(cg),
            self._key_findings(cg),
            self._evidence_table(cg),
            self._timeline(cg),
            self._for_against(cg, by_kind),
            self._unknowns(cg, by_kind),
            self._predictions(by_kind),
            self._related_discoveries(by_kind),
            self._confidence_scores(cg),
            self._source_references(cg, source_table),
        ]
        stats = {**run_stats, **consolidation, "datahub": datahub_status,
                 "sections": len(sections),
                 "sections_with_content": sum(1 for s in sections if s.item_count > 0)}
        return ResearchReport(session_id=cg.session_id, topic=cg.plan.topic,
                              sections=sections, stats=stats)

    # -- section builders -------------------------------------------------
    async def _exec_summary(self, cg: ContextGraph,
                            by_kind: dict[str, list[Finding]]) -> ReportSection:
        summaries = [f.text for f in by_kind.get("summary", [])][:6]
        top = [f"{e.name} (confidence {conf})" for e, conf, _n in cg.top_entities(6)]
        basis = (f"Topic: {cg.plan.topic}\nTop entities: {', '.join(top)}\n"
                 "Branch summaries:\n" + "\n".join(f"- {s}" for s in summaries))
        if not summaries and not top:
            return _empty("Executive Summary", "No evidence was gathered in this session")
        try:
            prose = await self.llm.chat_text(
                "summarize",
                "Write a 4-7 sentence executive research summary strictly from the "
                "material below. Plain prose, no bullets, no invented facts.",
                basis)
        except LLMUnavailable:
            prose = " ".join(summaries)[:1200] or "LLM unavailable; see Key Findings."
        return ReportSection(title="Executive Summary", body_md=prose.strip(),
                             item_count=max(len(summaries), 1))

    def _what_changed(self, by_kind: dict[str, list[Finding]]) -> ReportSection:
        trends = by_kind.get("trend", [])
        if not trends:
            return _empty("What Changed Recently?",
                          "No measurable recent acceleration in the dated evidence")
        body = "\n".join(f"- {f.text} _(confidence {f.confidence})_" for f in trends)
        return ReportSection(title="What Changed Recently?", body_md=body,
                             item_count=len(trends))

    def _consensus(self, cg: ContextGraph) -> ReportSection:
        rows = [c for c in cg.claims.values()
                if c.verified and len({e.source for e in c.evidence}) >= 2]
        rows.sort(key=lambda c: c.confidence, reverse=True)
        if not rows:
            single = [c for c in cg.claims.values() if c.verified]
            if not single:
                return _empty("What Is the Consensus?", "No claims cleared the verification gate")
            body = ("_No multi-source consensus formed; the following verified claims "
                    "rest on single high-reliability sources:_\n" +
                    "\n".join(f"- {c.statement} _(confidence {c.confidence})_"
                              for c in single[:8]))
            return ReportSection(title="What Is the Consensus?", body_md=body,
                                 item_count=len(single[:8]))
        body = "\n".join(
            f"- {c.statement} — corroborated by "
            f"{len({e.source for e in c.evidence})} sources _(confidence {c.confidence})_"
            for c in rows[:10])
        return ReportSection(title="What Is the Consensus?", body_md=body,
                             item_count=len(rows[:10]))

    def _uncertain(self, cg: ContextGraph,
                   by_kind: dict[str, list[Finding]]) -> ReportSection:
        items = [f"- {f.text}" for f in by_kind.get("question", [])]
        items += [f"- Contested: {f.text}" for f in by_kind.get("contradiction", [])[:4]]
        if not items:
            return _empty("What Remains Uncertain?",
                          "All planned questions were covered by verified evidence")
        return ReportSection(title="What Remains Uncertain?",
                             body_md="\n".join(items), item_count=len(items))

    def _connections(self, by_kind: dict[str, list[Finding]]) -> ReportSection:
        disc = by_kind.get("discovery", [])
        if not disc:
            return _empty("What Connections Were Discovered?",
                          "No cross-domain connections surfaced this session")
        body = "\n".join(f"- {f.text} _(confidence {f.confidence})_" for f in disc)
        return ReportSection(title="What Connections Were Discovered?",
                             body_md=body, item_count=len(disc))

    def _research_map(self, cg: ContextGraph) -> ReportSection:
        """The branch tree: topic → agents → documents-consulted counts."""
        if not cg.branches:
            return _empty("Research Map", "No research branches executed")
        lines = [f"**{cg.plan.topic}**", ""]
        for agent, urls in sorted(cg.branches.items(), key=lambda kv: -len(kv[1])):
            lines.append(f"- {agent} — {len(urls)} documents")
            for url in urls[:3]:
                lines.append(f"  - {url}")
            if len(urls) > 3:
                lines.append(f"  - … {len(urls) - 3} more")
        return ReportSection(title="Research Map", body_md="\n".join(lines),
                             item_count=len(cg.branches))

    def _major_entities(self, cg: ContextGraph) -> ReportSection:
        rows = cg.top_entities(15)
        if not rows:
            return _empty("Major Entities", "No entities were extracted")
        lines = ["| Entity | Type | Claims | Confidence | Description |",
                 "|---|---|---|---|---|"]
        for ent, conf, mentions in rows:
            desc = ent.description[:90].replace("|", "/")
            lines.append(f"| {ent.name} | {ent.type.value} | {mentions} | {conf} | {desc} |")
        return ReportSection(title="Major Entities", body_md="\n".join(lines),
                             item_count=len(rows))

    def _key_findings(self, cg: ContextGraph) -> ReportSection:
        verified = sorted((c for c in cg.claims.values() if c.verified),
                          key=lambda c: c.confidence, reverse=True)[:12]
        if not verified:
            return _empty("Key Findings", "No claims cleared the verification gate")
        body = "\n".join(
            f"{i}. {c.statement} _(confidence {c.confidence}; "
            f"{len({e.source for e in c.evidence})} source(s))_"
            for i, c in enumerate(verified, 1))
        return ReportSection(title="Key Findings", body_md=body,
                             item_count=len(verified))

    def _evidence_table(self, cg: ContextGraph) -> ReportSection:
        # one row per DOCUMENT: many claims cite the same source doc, and the
        # table must not inflate the evidence base by repeating it
        by_url: dict[str, object] = {}
        for ev in cg.evidence_by_id().values():
            best = by_url.get(ev.url)
            if best is None or ev.reliability > best.reliability:
                by_url[ev.url] = ev
        evs = sorted(by_url.values(), key=lambda e: e.reliability, reverse=True)
        rows = evs[:25]
        if not rows:
            return _empty("Evidence Table", "No evidence collected")
        lines = ["| Source | Title | Date | Author(s) | Reliability |",
                 "|---|---|---|---|---|"]
        for ev in rows:
            date = ev.published.date().isoformat() if ev.published else "—"
            authors = (", ".join(a for a in ev.authors if a)[:40] or "—").replace("|", "/")
            title = (ev.title[:60] or ev.url[:60]).replace("|", "/")
            lines.append(f"| {ev.source} | [{title}]({ev.url}) | {date} | {authors} | "
                f"{ev.reliability} |")
        return ReportSection(title="Evidence Table", body_md="\n".join(lines),
                             item_count=len(rows))

    def _timeline(self, cg: ContextGraph) -> ReportSection:
        events: list[TimelineEvent] = []
        seen_urls: set[str] = set()
        for c in cg.claims.values():
            for ev in c.evidence:
                if ev.published and ev.url not in seen_urls:
                    seen_urls.add(ev.url)
                    events.append(TimelineEvent(date=ev.published,
                                                text=ev.title or c.statement[:80],
                                                source=ev.source, url=ev.url))
        events.sort(key=lambda e: e.date)
        picks = events[-15:]
        if not picks:
            return _empty("Timeline", "No dated evidence available")
        body = "\n".join(f"- **{e.date.date()}** — {e.text[:100]} _({e.source})_"
                         for e in picks)
        return ReportSection(title="Timeline", body_md=body, item_count=len(picks))

    def _for_against(self, cg: ContextGraph,
                     by_kind: dict[str, list[Finding]]) -> ReportSection:
        asserts = [c for c in cg.claims.values()
                   if c.polarity == Polarity.ASSERTS and c.verified]
        disputes = [c for c in cg.claims.values() if c.polarity == Polarity.DISPUTES]
        contras = by_kind.get("contradiction", [])
        if not disputes and not contras:
            return _empty("Arguments For/Against",
                          "No disputed claims surfaced — the collected evidence points one way")
        lines = ["**Supporting positions**"]
        lines += [f"- {c.statement} _(confidence {c.confidence})_" for c in asserts[:6]] or ["- "
            "(none verified)"]
        lines += ["", "**Dissenting / disputing positions**"]
        lines += [f"- {c.statement} _(confidence {c.confidence})_" for c in disputes[:6]]
        if contras:
            lines += ["", "**Confirmed disagreements**"]
            lines += [f"- {f.text}" for f in contras[:4]]
        count = min(len(asserts), 6) + min(len(disputes), 6) + min(len(contras), 4)
        return ReportSection(title="Arguments For/Against",
                             body_md="\n".join(lines), item_count=count)

    def _unknowns(self, cg: ContextGraph,
                  by_kind: dict[str, list[Finding]]) -> ReportSection:
        items = list(cg.plan.unknowns)
        items += [f.text for f in by_kind.get("question", [])
                  if f.text.startswith("Unresolved:")]
        items = list(dict.fromkeys(items))[:10]  # dedupe, keep order
        if not items:
            return _empty("Unknowns", "The plan declared no unknowns and none emerged")
        return ReportSection(title="Unknowns",
                             body_md="\n".join(f"- {u}" for u in items),
                             item_count=len(items))

    def _predictions(self, by_kind: dict[str, list[Finding]]) -> ReportSection:
        trends = by_kind.get("trend", [])
        if not trends:
            return _empty("Future Predictions",
                          "No trend signal strong enough to extrapolate — declining to guess")
        lines = ["_Extrapolations from measured evidence acceleration — "
                 "model output, not established fact:_", ""]
        for f in trends[:6]:
            name = f.text.split("—")[0].replace("Emerging:", "").strip()
            lines.append(f"- If the current evidence rate holds, **{name}** continues "
                         f"gaining attention over the next 2-4 quarters "
                         f"_(basis confidence {f.confidence})_")
        return ReportSection(title="Future Predictions", body_md="\n".join(lines),
                             item_count=min(len(trends), 6))

    def _related_discoveries(self, by_kind: dict[str, list[Finding]]) -> ReportSection:
        disc = by_kind.get("discovery", [])
        summaries = by_kind.get("summary", [])
        items = [f"- {f.text}" for f in disc]
        if not items and summaries:
            return _empty("Related Discoveries",
                          "No adjacent findings beyond the direct topic this session")
        if not items:
            return _empty("Related Discoveries", "No discoveries recorded")
        return ReportSection(title="Related Discoveries", body_md="\n".join(items),
                             item_count=len(items))

    def _confidence_scores(self, cg: ContextGraph) -> ReportSection:
        rows = cg.top_entities(12)
        if not rows:
            return _empty("Confidence Scores", "Nothing to score")
        lines = ["| Entity | Confidence | Basis |", "|---|---|---|"]
        for ent, conf, mentions in rows:
            sources = {ev.source for c in cg.claims.values()
                       if ent.id in c.entity_ids for ev in c.evidence}
            lines.append(f"| {ent.name} | {conf} | {mentions} claims, "
                         f"{len(sources)} independent source(s) |")
        lines += ["", "_Confidence = mean evidence reliability + corroboration bonus "
                      "(deterministic; see extraction/reliability.py)._"]
        return ReportSection(title="Confidence Scores", body_md="\n".join(lines),
                             item_count=len(rows))

    def _source_references(self, cg: ContextGraph,
                           source_table: list[dict]) -> ReportSection:
        lines = ["**Source fleet status (this run)**", "",
                 "| Source | Category | Status | Calls | Docs | Note |",
                 "|---|---|---|---|---|---|"]
        for row in source_table:
            lines.append(f"| {row['source']} | {row['category']} | {row['status']} "
                         f"| {row['calls']} | {row['docs']} | {row['detail'][:60]} |")
        urls = sorted({ev.url for c in cg.claims.values() for ev in c.evidence})
        lines += ["", f"**Documents cited: {len(urls)}**", ""]
        lines += [f"- {u}" for u in urls[:40]]
        if len(urls) > 40:
            lines.append(f"- … {len(urls) - 40} more in the session file")
        return ReportSection(title="Source References", body_md="\n".join(lines),
                             item_count=len(source_table) + len(urls))

    # ------------------------------------------------------------------ #
    @staticmethod
    def to_markdown(report: ResearchReport) -> str:
        head = [f"# Research Report: {report.topic}",
                f"_Session `{report.session_id}` · generated "
                    f"{report.generated_at:%Y-%m-%d %H:%M UTC}_",
                "",
                "**Run stats:** " + ", ".join(f"{k}={v}" for k, v in report.stats.items()
                                              if not isinstance(v, dict)),
                ""]
        parts = []
        for s in report.sections:
            parts.append(f"## {s.title}\n\n{s.body_md}\n")
        return "\n".join(head + parts)

    @staticmethod
    def save_markdown(report: ResearchReport, out_dir: Path) -> Path:
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"{report.session_id}.md"
        path.write_text(ReportBuilder.to_markdown(report))
        return path
