"""Academic sources — all live keyless.

arXiv (Atom API), OpenAlex, Semantic Scholar (public tier), PubMed (NCBI
eutils), Crossref (which also indexes ACM/IEEE *metadata*, giving honest
partial coverage of paywalled venues without pretending to full text).
"""

from __future__ import annotations

from datetime import UTC, datetime

import feedparser

from ..models import RawDoc, SourceCategory
from .base import SourceAdapter


def _dt(value: str | None, fmt: str | None = None) -> datetime | None:
    if not value:
        return None
    try:
        if fmt:
            return datetime.strptime(value, fmt).replace(tzinfo=UTC)
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


class ArxivAdapter(SourceAdapter):
    name = "arxiv"
    category = SourceCategory.ACADEMIC
    reliability_prior = 0.75  # preprints: strong but unrefereed
    min_interval_s = 3.0      # arXiv asks for 3s between requests

    async def _search(self, query: str, k: int) -> list[RawDoc]:
        r = await self.client.get(
            "https://export.arxiv.org/api/query",
            params={"search_query": f"all:{query}", "max_results": k,
                    "sortBy": "relevance"})
        r.raise_for_status()
        feed = feedparser.parse(r.text)
        docs = []
        for e in feed.entries[:k]:
            docs.append(RawDoc(
                url=e.get("link", ""),
                title=e.get("title", "").replace("\n", " ").strip(),
                source=self.name, category=self.category,
                text=e.get("summary", "")[:4000],
                authors=[a.get("name", "") for a in e.get("authors", [])][:8],
                published=_dt(e.get("published")),
            ))
        return docs


class OpenAlexAdapter(SourceAdapter):
    name = "openalex"
    category = SourceCategory.ACADEMIC
    reliability_prior = 0.8   # aggregated, citation-counted scholarly index
    min_interval_s = 0.2

    async def _search(self, query: str, k: int) -> list[RawDoc]:
        r = await self.client.get(
            "https://api.openalex.org/works",
            params={"search": query, "per-page": k, "sort": "relevance_score:desc"})
        r.raise_for_status()
        docs = []
        for w in r.json().get("results", [])[:k]:
            # OpenAlex stores abstracts as an inverted index; reconstruct it.
            abstract = ""
            inv = w.get("abstract_inverted_index")
            if inv:
                positions: dict[int, str] = {}
                for word, idxs in inv.items():
                    for i in idxs:
                        positions[i] = word
                abstract = " ".join(positions[i] for i in sorted(positions))[:4000]
            docs.append(RawDoc(
                url=w.get("doi") or w.get("id", ""),
                title=w.get("display_name", "") or "",
                source=self.name, category=self.category,
                text=abstract,
                authors=[a.get("author", {}).get("display_name", "")
                         for a in w.get("authorships", [])][:8],
                published=_dt(w.get("publication_date"), "%Y-%m-%d"),
                extra={"cited_by": w.get("cited_by_count", 0)},
            ))
        return docs


class SemanticScholarAdapter(SourceAdapter):
    name = "semantic_scholar"
    category = SourceCategory.ACADEMIC
    reliability_prior = 0.8
    min_interval_s = 1.2      # public tier is ~1 rps; stay under it
    concurrency = 1

    async def _search(self, query: str, k: int) -> list[RawDoc]:
        r = await self.client.get(
            "https://api.semanticscholar.org/graph/v1/paper/search",
            params={"query": query, "limit": min(k, 20),
                    "fields": "title,abstract,url,year,citationCount,authors,publicationDate"})
        r.raise_for_status()
        docs = []
        for p in r.json().get("data", [])[:k]:
            docs.append(RawDoc(
                url=p.get("url") or "",
                title=p.get("title") or "",
                source=self.name, category=self.category,
                text=(p.get("abstract") or "")[:4000],
                authors=[a.get("name", "") for a in (p.get("authors") or [])][:8],
                published=_dt(p.get("publicationDate"), "%Y-%m-%d"),
                extra={"cited_by": p.get("citationCount", 0)},
            ))
        return docs


class PubMedAdapter(SourceAdapter):
    name = "pubmed"
    category = SourceCategory.ACADEMIC
    reliability_prior = 0.85  # peer-reviewed biomedical literature
    min_interval_s = 0.4      # NCBI allows 3 rps keyless

    async def _search(self, query: str, k: int) -> list[RawDoc]:
        base = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
        r = await self.client.get(f"{base}/esearch.fcgi",
                                  params={"db": "pubmed", "term": query,
                                          "retmax": k, "retmode": "json"})
        r.raise_for_status()
        ids = r.json().get("esearchresult", {}).get("idlist", [])
        if not ids:
            return []
        await self._throttle()
        r2 = await self.client.get(f"{base}/esummary.fcgi",
                                   params={"db": "pubmed", "id": ",".join(ids),
                                           "retmode": "json"})
        r2.raise_for_status()
        result = r2.json().get("result", {})
        docs = []
        for pid in ids:
            item = result.get(pid)
            if not item:
                continue
            docs.append(RawDoc(
                url=f"https://pubmed.ncbi.nlm.nih.gov/{pid}/",
                title=item.get("title", ""),
                source=self.name, category=self.category,
                text=item.get("title", ""),  # esummary has no abstract; title-level evidence
                authors=[a.get("name", "") for a in item.get("authors", [])][:8],
                published=_dt(item.get("pubdate"), "%Y %b %d") or _dt(item.get("pubdate"), "%Y %b"),
            ))
        return docs


class CrossrefAdapter(SourceAdapter):
    name = "crossref"
    category = SourceCategory.ACADEMIC
    reliability_prior = 0.75
    min_interval_s = 0.5

    async def _search(self, query: str, k: int) -> list[RawDoc]:
        r = await self.client.get(
            "https://api.crossref.org/works",
            params={"query": query, "rows": k, "select": "title,DOI,abstract,author,issued,URL,container-title"})
        r.raise_for_status()
        docs = []
        for it in r.json().get("message", {}).get("items", [])[:k]:
            issued = it.get("issued", {}).get("date-parts", [[None]])[0]
            pub = None
            if issued and issued[0]:
                parts = (list(issued) + [1, 1])[:3]
                try:
                    pub = datetime(parts[0], parts[1] or 1, parts[2] or 1, tzinfo=UTC)
                except (TypeError, ValueError):
                    pub = None
            docs.append(RawDoc(
                url=it.get("URL", ""),
                title=" ".join(it.get("title", []) or [""]),
                source=self.name, category=self.category,
                text=(it.get("abstract") or "")[:4000],
                authors=[f"{a.get('given','')} {a.get('family','')}".strip()
                         for a in it.get("author", [])][:8],
                published=pub,
                extra={"venue": " ".join(it.get("container-title", []) or [])},
            ))
        return docs
