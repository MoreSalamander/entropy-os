"""Phase 2 — Parallel Software Research.

Six research workers run concurrently, reusing the research-engine fleet
plus three sources this engine adds:

  Technology Research      PyPI JSON API (live, keyless): candidate library
                           metadata, latest versions, maintenance signals
  Architecture Research    Wikipedia + Hacker News: patterns, prior systems
  Open Source Research     GitHub: reference implementations, stars
  Documentation Research   PageFetcher on official docs of stack candidates
  Security Research        OSV.dev (live, keyless): known vulnerabilities
                           for the candidate dependency set
  UX Research              HN + Wikipedia: comparable products, workflows

Parallel.ai rides along as a keyed adapter (PARALLEL_API_KEY): when a key
exists it widens every worker's discovery; without one it reports itself
fail-closed like every keyed source in this family.
"""

from __future__ import annotations

import asyncio

import httpx

from entropy_os.engines.research.models import RawDoc, SourceCategory, SourceStatus
from entropy_os.engines.research.sources.base import USER_AGENT, KeyedAdapter
from entropy_os.engines.research.sources.code import GitHubAdapter
from entropy_os.engines.research.sources.community import HackerNewsAdapter
from entropy_os.engines.research.sources.web import PageFetcher, WikipediaAdapter

from .models import ResearchEvidence, SoftwareSpec

RESEARCH_AGENTS = ["Technology Research Agent", "Architecture Research Agent",
                   "Open Source Research Agent", "Documentation Research Agent",
                   "Security Research Agent", "UX Research Agent"]

# The stack this engine generates, plus common candidates worth researching.
_CANDIDATE_PACKAGES = ["fastapi", "sqlalchemy", "pydantic", "uvicorn",
                       "httpx", "pytest"]

_DOC_URLS = {
    "fastapi": "https://fastapi.tiangolo.com/",
    "sqlalchemy": "https://docs.sqlalchemy.org/en/20/",
    "pydantic": "https://docs.pydantic.dev/latest/",
}


class ParallelSearchAdapter(KeyedAdapter):
    """Parallel.ai web search — the spec's named provider. Keyed, fail-closed."""
    name = "parallel_ai"
    category = SourceCategory.WEB
    reliability_prior = 0.55
    key_hint = "PARALLEL_API_KEY — https://parallel.ai"

    async def _search(self, query: str, k: int) -> list[RawDoc]:
        r = await self.client.post(
            "https://api.parallel.ai/v1beta/search",
            json={"objective": query, "max_results": k},
            headers={"x-api-key": self.api_key})
        r.raise_for_status()
        return [RawDoc(url=res.get("url", ""), title=res.get("title", ""),
                       source=self.name, category=self.category,
                       text=" ".join(res.get("excerpts", []))[:2000])
                for res in r.json().get("results", [])[:k]]


class SoftwareResearchOrchestrator:
    def __init__(self, parallel_key: str = ""):
        self.client = httpx.AsyncClient(
            headers={"User-Agent": USER_AGENT}, timeout=httpx.Timeout(20.0),
            follow_redirects=True, limits=httpx.Limits(max_connections=16))
        self.github = GitHubAdapter(self.client)
        self.hn = HackerNewsAdapter(self.client)
        self.wiki = WikipediaAdapter(self.client)
        self.fetcher = PageFetcher(self.client)
        self.parallel = ParallelSearchAdapter(self.client, parallel_key)

    # -- live keyless additions ----------------------------------------
    async def pypi_info(self, package: str) -> ResearchEvidence | None:
        try:
            r = await self.client.get(f"https://pypi.org/pypi/{package}/json")
            r.raise_for_status()
            info = r.json().get("info", {})
            return ResearchEvidence(
                agent="Technology Research Agent", topic="technology",
                title=f"{package} {info.get('version', '?')}",
                url=info.get("project_url") or f"https://pypi.org/project/{package}/",
                summary=(info.get("summary") or "")[:200],
                extra={"version": info.get("version", ""),
                       "requires_python": info.get("requires_python") or ""})
        except httpx.HTTPError:
            return None

    async def osv_query(self, packages: list[str]) -> list[ResearchEvidence]:
        """Real vulnerability lookup for the candidate dependency set."""
        try:
            r = await self.client.post(
                "https://api.osv.dev/v1/querybatch",
                json={"queries": [{"package": {"name": p, "ecosystem": "PyPI"}}
                                  for p in packages]})
            r.raise_for_status()
            out: list[ResearchEvidence] = []
            for pkg, res in zip(packages, r.json().get("results", []), strict=True):
                vulns = res.get("vulns") or []
                out.append(ResearchEvidence(
                    agent="Security Research Agent", topic="security",
                    title=f"OSV: {pkg} — {len(vulns)} known advisories (all versions)",
                    url=f"https://osv.dev/list?ecosystem=PyPI&q={pkg}",
                    summary=", ".join(v.get("id", "?") for v in vulns[:6]),
                    extra={"package": pkg, "advisories": len(vulns)}))
            return out
        except httpx.HTTPError:
            return []

    # -- workers ---------------------------------------------------------
    async def _technology(self, spec: SoftwareSpec) -> list[ResearchEvidence]:
        results = await asyncio.gather(
            *(self.pypi_info(p) for p in _CANDIDATE_PACKAGES))
        return [r for r in results if r]

    async def _architecture(self, spec: SoftwareSpec) -> list[ResearchEvidence]:
        out: list[ResearchEvidence] = []
        for query in (spec.candidate_approaches[:2] or [spec.purpose]):
            for doc in await self.wiki.search(query, 2):
                out.append(ResearchEvidence(
                    agent="Architecture Research Agent", topic="architecture",
                    title=doc.title, url=doc.url, summary=doc.text[:200]))
        for doc in await self.hn.search(f"{spec.purpose[:60]} architecture", 4):
            out.append(ResearchEvidence(
                agent="Architecture Research Agent", topic="architecture",
                title=doc.title, url=doc.url,
                extra={"points": doc.extra.get("points", 0)}))
        return out

    async def _opensource(self, spec: SoftwareSpec) -> list[ResearchEvidence]:
        query = f"{spec.purpose[:50]}"
        docs = await self.github.search(query, 6)
        docs += await self.parallel.search(f"open source {query}", 4)
        return [ResearchEvidence(
            agent="Open Source Research Agent", topic="opensource",
            title=d.title, url=d.url, summary=d.text[:200],
            extra={"stars": d.extra.get("stars", 0)}) for d in docs]

    async def _documentation(self, spec: SoftwareSpec) -> list[ResearchEvidence]:
        out: list[ResearchEvidence] = []
        for name, url in _DOC_URLS.items():
            text = await self.fetcher.fetch_text(url, max_chars=1200)
            if text:
                out.append(ResearchEvidence(
                    agent="Documentation Research Agent", topic="docs",
                    title=f"{name} official documentation", url=url,
                    summary=text[:250]))
        return out

    async def _security(self, spec: SoftwareSpec) -> list[ResearchEvidence]:
        evidence = await self.osv_query(_CANDIDATE_PACKAGES)
        for doc in await self.hn.search("fastapi security best practices", 3):
            evidence.append(ResearchEvidence(
                agent="Security Research Agent", topic="security",
                title=doc.title, url=doc.url))
        return evidence

    async def _ux(self, spec: SoftwareSpec) -> list[ResearchEvidence]:
        out: list[ResearchEvidence] = []
        for doc in await self.hn.search(f"{spec.purpose[:60]}", 5):
            out.append(ResearchEvidence(
                agent="UX Research Agent", topic="ux",
                title=doc.title, url=doc.url,
                extra={"points": doc.extra.get("points", 0)}))
        return out

    # -- entry point -----------------------------------------------------
    async def run(self, spec: SoftwareSpec) -> tuple[list[ResearchEvidence], dict]:
        batches = await asyncio.gather(
            self._technology(spec), self._architecture(spec),
            self._opensource(spec), self._documentation(spec),
            self._security(spec), self._ux(spec))
        evidence = [e for batch in batches for e in batch]
        stats = {
            "workers": dict(zip(RESEARCH_AGENTS, (len(b) for b in batches), strict=True)),
            "evidence_total": len(evidence),
            "parallel_ai": (self.parallel.status.value
                            if self.parallel.status != SourceStatus.LIVE
                            else "live"),
        }
        return evidence, stats

    async def aclose(self) -> None:
        await self.client.aclose()
