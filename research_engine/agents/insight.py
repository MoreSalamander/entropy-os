"""Insight agents: Research Analyst, Discovery, Trend, Question.

Same law as the gate pair — deterministic structure first, LLM voices last:
  Analyst    summarizes per research branch from claims that exist
  Discovery  finds non-obvious connections by graph traversal (paths whose
             evidence spans DIFFERENT source categories), then names them
  Trend      time-buckets dated evidence per entity; "emerging" is a
             measured acceleration, not an adjective
  Question   turns unsupported plan questions + weak entities into concrete
             follow-up research paths (which feed the next session's plan)
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone

from ..graphs.context_graph import ContextGraph
from ..graphs.knowledge_graph import KnowledgeGraph
from ..llm.client import LLMUnavailable
from ..models import Finding
from .base import GraphAgent


class AnalystAgent(GraphAgent):
    """Summarizes findings per research branch. The summary prose is LLM-voiced
    but built ONLY from verified/high-confidence claim statements passed in —
    the model is given nothing to summarize but the evidence-backed record."""

    name = "Research Analyst Agent"
    MAX_BRANCHES = 6
    CLAIMS_PER_BRANCH = 12

    async def analyze(self, cg: ContextGraph,
                      kg: KnowledgeGraph | None = None) -> list[Finding]:
        findings: list[Finding] = []
        # branch = the agent that produced the claim (recorded at ingestion,
        # not inferred from URLs); strongest claims first
        by_branch: dict[str, list] = defaultdict(list)
        for cid, claim in cg.claims.items():
            by_branch[cg.claim_branch.get(cid, "General")].append(claim)

        for branch, claims in list(by_branch.items())[: self.MAX_BRANCHES]:
            top = sorted(claims, key=lambda c: c.confidence, reverse=True)[: self.CLAIMS_PER_BRANCH]
            if not top:
                continue
            record = "\n".join(f"- {c.statement} (confidence {c.confidence})" for c in top)
            try:
                prose = await self.llm.chat_text(
                    "summarize",
                    "Summarize these evidence-backed research findings in 2-4 plain "
                    "sentences. Use ONLY the statements given. No speculation.",
                    f"Branch: {branch}\n{record}")
            except LLMUnavailable:
                prose = "; ".join(c.statement for c in top[:3])  # degraded but honest
            findings.append(Finding(
                agent=self.name, kind="summary",
                text=f"[{branch}] {prose.strip()[:800]}",
                entity_ids=list({e for c in top for e in c.entity_ids})[:10],
                evidence_ids=[ev.id for c in top for ev in c.evidence][:20],
                confidence=round(sum(c.confidence for c in top) / len(top), 3)))
        return findings


class DiscoveryAgent(GraphAgent):
    """Hidden connections = entity pairs linked through ≥2 intermediate hops
    whose supporting evidence comes from DIFFERENT source categories.
    Same-category paths are ordinary; cross-category paths are where the
    'academic paper ↔ shipping product ↔ regulation' surprises live."""

    name = "Discovery Agent"
    MAX_FINDINGS = 8

    async def analyze(self, cg: ContextGraph,
                      kg: KnowledgeGraph | None = None) -> list[Finding]:
        findings: list[Finding] = []
        # category each entity was evidenced by
        ent_cats: dict[str, set[str]] = defaultdict(set)
        for claim in cg.claims.values():
            for eid in claim.entity_ids:
                for ev in claim.evidence:
                    ent_cats[eid].add(ev.category.value)

        top = [e.id for e, _conf, _n in cg.top_entities(12)]
        seen_pairs: set[tuple[str, str]] = set()
        import networkx as nx
        ug = cg.g.to_undirected(as_view=True)
        for i, a in enumerate(top):
            for b in top[i + 1:]:
                if len(findings) >= self.MAX_FINDINGS:
                    return findings
                pair = (min(a, b), max(a, b))
                if pair in seen_pairs or not (ent_cats[a] and ent_cats[b]):
                    continue
                seen_pairs.add(pair)
                if not ent_cats[a].isdisjoint(ent_cats[b]):
                    continue  # shared category → not a cross-domain discovery
                try:
                    path = nx.shortest_path(ug, a, b)
                except (nx.NetworkXNoPath, nx.NodeNotFound):
                    continue
                if not (2 <= len(path) - 1 <= 4):
                    continue  # direct links are obvious; distant ones are noise
                names = [cg.entities[n].name if n in cg.entities
                         else cg.claims[n].statement[:40] if n in cg.claims else n
                         for n in path]
                findings.append(Finding(
                    agent=self.name, kind="discovery",
                    text=(f"Cross-domain connection ({'/'.join(sorted(ent_cats[a]))} ↔ "
                          f"{'/'.join(sorted(ent_cats[b]))}): " + " → ".join(names)),
                    entity_ids=[a, b],
                    confidence=round(min(cg.entity_confidence(a),
                                         cg.entity_confidence(b)), 3)))
        return findings


class TrendAgent(GraphAgent):
    """Emerging = measured: an entity whose dated evidence in the most recent
    90-day bucket exceeds its trailing-year average bucket by 2x with ≥3
    recent items. Also reports the overall recent-activity picture that the
    report's 'What changed recently?' section is built from."""

    name = "Trend Agent"
    RECENT_DAYS = 90

    async def analyze(self, cg: ContextGraph,
                      kg: KnowledgeGraph | None = None) -> list[Finding]:
        now = datetime.now(timezone.utc)
        recent_cut = now - timedelta(days=self.RECENT_DAYS)
        year_cut = now - timedelta(days=365)

        recent: dict[str, int] = defaultdict(int)
        trailing: dict[str, int] = defaultdict(int)
        for claim in cg.claims.values():
            for ev in claim.evidence:
                if ev.published is None:
                    continue
                for eid in claim.entity_ids:
                    if ev.published >= recent_cut:
                        recent[eid] += 1
                    elif ev.published >= year_cut:
                        trailing[eid] += 1

        findings: list[Finding] = []
        for eid, r_count in sorted(recent.items(), key=lambda kv: -kv[1]):
            if eid not in cg.entities or r_count < 3:
                continue
            # trailing year has 3 trailing 90-day buckets; compare per-bucket
            baseline = trailing[eid] / 3.0
            if baseline == 0 or r_count >= 2.0 * baseline:
                ent = cg.entities[eid]
                findings.append(Finding(
                    agent=self.name, kind="trend",
                    text=(f"Emerging: {ent.name} — {r_count} evidence items in the "
                          f"last {self.RECENT_DAYS} days vs {baseline:.1f}/quarter "
                          f"trailing baseline"),
                    entity_ids=[eid],
                    confidence=cg.entity_confidence(eid)))
            if len(findings) >= 8:
                break
        return findings


class QuestionAgent(GraphAgent):
    """Creates follow-up research paths from what the session did NOT settle:
    plan questions with no verified claim coverage, plus high-mention
    low-confidence entities. Deterministic selection; LLM only phrases the
    follow-up query."""

    name = "Question Agent"

    COVERAGE_THRESHOLD = 0.7  # fraction of a question's content words that
    #                           verified claims must contain to call it settled

    async def analyze(self, cg: ContextGraph,
                      kg: KnowledgeGraph | None = None) -> list[Finding]:
        findings: list[Finding] = []
        verified_words = {w.strip("?.,!:;()\"'")
                          for c in cg.claims.values() if c.verified
                          for w in c.statement.casefold().split()}

        for question in cg.open_questions:
            # deterministic coverage test on whole words (substring matching
            # is a trap: "state" hides inside "overstated")
            words = [w.strip("?.,!:;()\"'") for w in question.casefold().split()]
            words = [w for w in words if len(w) > 4]
            covered = (words and sum(w in verified_words for w in words) / len(words)
                       >= self.COVERAGE_THRESHOLD)
            if not covered:
                findings.append(Finding(
                    agent=self.name, kind="question",
                    text=f"Unresolved: {question}",
                    confidence=0.0))

        for ent, conf, mentions in cg.top_entities(10):
            if mentions >= 3 and conf < 0.5:
                findings.append(Finding(
                    agent=self.name, kind="question",
                    text=(f"Follow-up path: '{ent.name}' is heavily referenced "
                          f"({mentions} claims) but weakly evidenced "
                          f"(confidence {conf}) — targeted search warranted"),
                    entity_ids=[ent.id], confidence=conf))
        return findings[:12]
