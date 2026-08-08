"""Phase 2 — Parallel Semantic Web Intelligence.

Six research workers run CONCURRENTLY, each with its own focus and source
mix, all feeding one Context Graph:

  UX Research           seeds (award/saas) → section + conversion signals
  Visual Design         seeds (award tier) → typography / color / motion
  Branding              seeds (startup/industry) → positioning traits
  Competitor Analysis   discovery (HN keyless; Brave/Serper when keyed)
                        → fetch + analyze real competitor sites
  Industry Research     industry-tier seeds + Wikipedia industry context
  Frontend Architecture GitHub → component libraries / template ecosystems

Discovery reuses research-engine's source adapters unchanged (engine on
engine). "Semantic search" is honest about its mechanism: intent traits are
embedded and matched against OUR analyzed corpus (Context + Knowledge
Graph) — the open web is only reachable through the seed corpus, keyless
community/code adapters, and the keyed web-search adapters when configured.
"""

from __future__ import annotations

import asyncio
import re
from urllib.parse import urlparse

import httpx

from research_engine.sources.base import USER_AGENT
from research_engine.sources.code import GitHubAdapter
from research_engine.sources.community import HackerNewsAdapter
from research_engine.sources.keyed import BraveSearchAdapter, SerperAdapter
from research_engine.sources.web import WikipediaAdapter

from ..graphs.context_graph import DesignContextGraph
from ..models import ProjectIntent, SiteAnalysis
from .seeds import seeds_for
from .site_analyzer import SiteAnalyzer

# domains that are press/aggregators, not competitor product sites
_NON_PRODUCT_HOSTS = re.compile(
    r"(news\.ycombinator|techcrunch|forbes|medium\.com|substack|youtube|twitter|x\.com|"
    r"linkedin|reddit|wikipedia|github\.com|bloomberg|reuters|wsj\.com|nytimes)")

RESEARCH_WORKERS = ["UX Research Agent", "Visual Design Agent", "Branding Agent",
                    "Competitor Analysis Agent", "Industry Research Agent",
                    "Frontend Architecture Agent"]


class DesignResearchOrchestrator:
    def __init__(self, brave_key: str = "", serper_key: str = "",
                 max_competitor_sites: int = 5):
        self.client = httpx.AsyncClient(
            headers={"User-Agent": USER_AGENT}, timeout=httpx.Timeout(20.0),
            follow_redirects=True,
            limits=httpx.Limits(max_connections=24))
        self.analyzer = SiteAnalyzer(self.client)
        self.hn = HackerNewsAdapter(self.client)
        self.wiki = WikipediaAdapter(self.client)
        self.github = GitHubAdapter(self.client)
        self.brave = BraveSearchAdapter(self.client, brave_key)
        self.serper = SerperAdapter(self.client, serper_key)
        self.max_competitors = max_competitor_sites

    # ------------------------------------------------------------------ #
    # workers (each returns analyses / evidence it contributed)
    # ------------------------------------------------------------------ #
    async def _analyze_seed_tier(self, worker: str, seeds: list[dict],
                                 cg: DesignContextGraph) -> int:
        results = await asyncio.gather(
            *(self.analyzer.analyze(s["url"], worker, s["category"]) for s in seeds))
        count = 0
        for analysis in results:
            cg.add_analysis(worker, analysis)
            count += int(analysis.ok)
        return count

    async def _ux_worker(self, intent: ProjectIntent, cg: DesignContextGraph) -> int:
        seeds = [s for s in seeds_for(intent.industry, intent.semantic_traits)
                 if s["category"] in ("award", "saas")]
        return await self._analyze_seed_tier("UX Research Agent", seeds, cg)

    async def _visual_worker(self, intent: ProjectIntent, cg: DesignContextGraph) -> int:
        seeds = [s for s in seeds_for(intent.industry, intent.semantic_traits)
                 if s["category"] == "award"]
        return await self._analyze_seed_tier("Visual Design Agent", seeds, cg)

    async def _branding_worker(self, intent: ProjectIntent, cg: DesignContextGraph) -> int:
        seeds = [s for s in seeds_for(intent.industry, intent.semantic_traits)
                 if s["category"] in ("startup", "industry")]
        return await self._analyze_seed_tier("Branding Agent", seeds, cg)

    async def _industry_worker(self, intent: ProjectIntent, cg: DesignContextGraph) -> int:
        count = await self._analyze_seed_tier(
            "Industry Research Agent",
            [s for s in seeds_for(intent.industry, intent.semantic_traits)
             if s["category"] in ("industry", "enterprise")], cg)
        # wikipedia gives industry CONTEXT (audience language, terminology)
        docs = await self.wiki.search(intent.industry, 3)
        for d in docs:
            cg.add_industry_note("Industry Research Agent", d.title, d.text, d.url)
        return count + len(docs)

    async def _competitor_worker(self, intent: ProjectIntent, cg: DesignContextGraph) -> int:
        """Discover competitor PRODUCT sites, then analyze them like any seed.
        Keyless path: HN story URLs filtered to non-press domains. Keyed path
        (Brave/Serper) widens this dramatically — status is reported either way."""
        urls: list[str] = []
        for adapter, query in ((self.brave, f"{intent.industry} company website"),
                               (self.serper, f"{intent.industry} startup")):
            for doc in await adapter.search(query, 8):
                urls.append(doc.url)
        hn_docs = await self.hn.search(intent.industry, 15)
        urls += [d.url for d in hn_docs]

        picked: list[str] = []
        seen_hosts: set[str] = set()
        for url in urls:
            host = urlparse(url).netloc.casefold()
            if (not host or host in seen_hosts
                    or _NON_PRODUCT_HOSTS.search(url.casefold())):
                continue
            seen_hosts.add(host)
            picked.append(f"https://{host}")
            if len(picked) >= self.max_competitors:
                break
        results = await asyncio.gather(
            *(self.analyzer.analyze(u, "Competitor Analysis Agent", "competitor")
              for u in picked))
        ok = 0
        for analysis in results:
            cg.add_analysis("Competitor Analysis Agent", analysis)
            ok += int(analysis.ok)
        cg.competitor_discovery_note = (
            f"{ok}/{len(picked)} competitor sites analyzed; discovery via "
            + ("keyed web search + HN" if (self.brave.api_key or self.serper.api_key)
               else "HN only (keyless best-effort — add a Brave/Serper key to widen)"))
        return ok

    async def _frontend_worker(self, intent: ProjectIntent, cg: DesignContextGraph) -> int:
        docs = await self.github.search("nextjs tailwind template components", 6)
        for d in docs:
            cg.add_tech_note("Frontend Architecture Agent", d.title,
                             d.text, d.url, stars=d.extra.get("stars", 0))
        return len(docs)

    # ------------------------------------------------------------------ #
    async def run(self, intent: ProjectIntent, cg: DesignContextGraph) -> dict:
        counts = await asyncio.gather(
            self._ux_worker(intent, cg),
            self._visual_worker(intent, cg),
            self._branding_worker(intent, cg),
            self._competitor_worker(intent, cg),
            self._industry_worker(intent, cg),
            self._frontend_worker(intent, cg),
        )
        return {
            "workers": dict(zip(RESEARCH_WORKERS, counts)),
            "sites_analyzed": len(cg.analyses),
            "sites_failed": sum(1 for a in cg.analyses.values() if not a.ok),
            "traits_extracted": sum(len(a.traits) for a in cg.analyses.values()),
            "competitor_note": cg.competitor_discovery_note,
        }

    async def aclose(self) -> None:
        await self.client.aclose()
