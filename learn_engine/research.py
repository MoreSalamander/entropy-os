"""Phase 2 — Parallel Educational Research Engine.

Six agents run concurrently per concept batch, all on reused live keyless
adapters. Each returns LearningResource rows typed by pedagogical role:

  Academic          arXiv + OpenAlex + Semantic Scholar (papers, lectures)
  Explanation       Wikipedia (baseline) + HN "explained/intuition" threads
  Practical         GitHub (projects, exercises, labs)
  Historical        Wikipedia history pages + Crossref
  Industry          HN + GDELT (current applications, career signal)
  Assessment        generates nothing here — it consumes the others' output
                    downstream (teaching.py); listed for org completeness

Open courseware rides Explanation via direct page fetches (MIT OCW search
pages are plain HTML) — best-effort, honestly flaky, contained.
"""

from __future__ import annotations

import asyncio

import httpx

from research_engine.sources.academic import (ArxivAdapter, CrossrefAdapter,
                                              OpenAlexAdapter,
                                              SemanticScholarAdapter)
from research_engine.sources.base import USER_AGENT
from research_engine.sources.code import GitHubAdapter
from research_engine.sources.community import HackerNewsAdapter
from research_engine.sources.news import GDELTAdapter
from research_engine.sources.web import PageFetcher, WikipediaAdapter

from .models import LearningResource

RESEARCH_AGENTS = ["Academic Research Agent", "Explanation Agent",
                   "Practical Learning Agent", "Historical Context Agent",
                   "Industry Agent", "Assessment Agent"]


def concepts_to_research(learning_order: list[str], cap: int) -> list[str]:
    """The FIRST `cap` concepts in learning order — teaching starts at the
    deepest prerequisites, so research must cover them first. (The initial
    live run sliced from the goal end and taught Calculus with zero
    resources; this helper exists so that mistake stays fixed and tested.)"""
    return learning_order[:cap]


class EducationalResearch:
    def __init__(self):
        self.client = httpx.AsyncClient(
            headers={"User-Agent": USER_AGENT}, timeout=httpx.Timeout(20.0),
            follow_redirects=True, limits=httpx.Limits(max_connections=16))
        self.arxiv = ArxivAdapter(self.client)
        self.openalex = OpenAlexAdapter(self.client)
        self.s2 = SemanticScholarAdapter(self.client)
        self.crossref = CrossrefAdapter(self.client)
        self.wiki = WikipediaAdapter(self.client)
        self.hn = HackerNewsAdapter(self.client)
        self.github = GitHubAdapter(self.client)
        self.gdelt = GDELTAdapter(self.client)
        self.fetcher = PageFetcher(self.client)

    def _rows(self, docs, concept: str, kind: str, agent: str,
              note: str = "") -> list[LearningResource]:
        return [LearningResource(concept_name=concept, kind=kind,
                                 title=d.title[:150], url=d.url,
                                 note=note or d.text[:150], agent=agent)
                for d in docs if d.url]

    # ---- agents --------------------------------------------------------
    async def _academic(self, concept: str) -> list[LearningResource]:
        a, o = await asyncio.gather(self.arxiv.search(concept, 2),
                                    self.openalex.search(concept, 2))
        s = await self.s2.search(f"{concept} tutorial survey", 2)
        return self._rows(a + o + s, concept, "paper", "Academic Research Agent")

    async def _explanation(self, concept: str) -> list[LearningResource]:
        w = await self.wiki.search(concept, 2)
        h = await self.hn.search(f"{concept} explained", 3)
        rows = self._rows(w, concept, "explanation", "Explanation Agent",
                          note="encyclopedic baseline")
        rows += self._rows(h, concept, "explanation", "Explanation Agent",
                           note="community explanation thread")
        # open courseware, best-effort
        ocw = f"https://ocw.mit.edu/search/?q={concept.replace(' ', '%20')}"
        text = await self.fetcher.fetch_text(ocw, max_chars=400)
        if text:
            rows.append(LearningResource(
                concept_name=concept, kind="explanation",
                title=f"MIT OCW search: {concept}", url=ocw,
                note="open courseware entry point", agent="Explanation Agent"))
        return rows

    async def _practical(self, concept: str) -> list[LearningResource]:
        g = await self.github.search(f"{concept} exercises tutorial", 4)
        return self._rows(g, concept, "project", "Practical Learning Agent")

    async def _historical(self, concept: str) -> list[LearningResource]:
        w = await self.wiki.search(f"history of {concept}", 2)
        c = await self.crossref.search(f"{concept} original paper", 2)
        return (self._rows(w, concept, "history", "Historical Context Agent")
                + self._rows(c, concept, "history", "Historical Context Agent",
                             note="primary literature"))

    async def _industry(self, concept: str) -> list[LearningResource]:
        h = await self.hn.search(f"{concept} in production", 3)
        n = await self.gdelt.search(concept, 2)
        return (self._rows(h, concept, "industry", "Industry Agent")
                + self._rows(n, concept, "industry", "Industry Agent",
                             note="recent coverage"))

    # ---- entry point ---------------------------------------------------
    async def research_concepts(self, concepts: list[str],
                                per_concept_agents: int = 5
                                ) -> tuple[list[LearningResource], dict]:
        """All agents × all concepts concurrently. `per_concept_agents`
        exists so callers can cheapen deep-prerequisite research."""
        async def one(concept: str) -> list[LearningResource]:
            workers = [self._academic(concept), self._explanation(concept),
                       self._practical(concept), self._historical(concept),
                       self._industry(concept)][:per_concept_agents]
            batches = await asyncio.gather(*workers, return_exceptions=True)
            out: list[LearningResource] = []
            for b in batches:
                if isinstance(b, list):
                    out.extend(b)
            return out

        results = await asyncio.gather(*(one(c) for c in concepts))
        resources = [r for batch in results for r in batch]
        by_agent: dict[str, int] = {}
        for r in resources:
            by_agent[r.agent] = by_agent.get(r.agent, 0) + 1
        return resources, {"resources_total": len(resources),
                           "by_agent": by_agent,
                           "concepts_researched": len(concepts)}

    async def aclose(self) -> None:
        await self.client.aclose()
