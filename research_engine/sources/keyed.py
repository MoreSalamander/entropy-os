"""Keyed adapters — the sources that DO NOT work without credentials.

This file is the up-front honesty list made executable. Every adapter here
ships fully implemented against its real API; without a key it reports
NEEDS_KEY, contributes nothing, and the report says so. Paste the key into
config.yaml (or the matching env var) and it goes live — no code changes.

WIPO is the one true stub: it has no practical free search API at all, so
its adapter exists only to state that honestly in the status table.
"""

from __future__ import annotations

from ..models import RawDoc, SourceCategory, SourceStatus
from .base import KeyedAdapter, SourceAdapter
from .academic import _dt


class BraveSearchAdapter(KeyedAdapter):
    name = "brave_search"
    category = SourceCategory.WEB
    reliability_prior = 0.5
    min_interval_s = 1.1
    key_hint = "sources.keys.brave_search (BRAVE_SEARCH_API_KEY) — https://brave.com/search/api/"

    async def _search(self, query: str, k: int) -> list[RawDoc]:
        r = await self.client.get(
            "https://api.search.brave.com/res/v1/web/search",
            params={"q": query, "count": k},
            headers={"X-Subscription-Token": self.api_key})
        r.raise_for_status()
        return [RawDoc(url=w.get("url", ""), title=w.get("title", ""),
                       source=self.name, category=self.category,
                       text=w.get("description", "")[:2000])
                for w in r.json().get("web", {}).get("results", [])[:k]]


class SerperAdapter(KeyedAdapter):
    name = "serper"
    category = SourceCategory.WEB
    reliability_prior = 0.5
    key_hint = "sources.keys.serper (SERPER_API_KEY) — https://serper.dev"

    async def _search(self, query: str, k: int) -> list[RawDoc]:
        r = await self.client.post(
            "https://google.serper.dev/search",
            json={"q": query, "num": k},
            headers={"X-API-KEY": self.api_key})
        r.raise_for_status()
        return [RawDoc(url=o.get("link", ""), title=o.get("title", ""),
                       source=self.name, category=self.category,
                       text=o.get("snippet", "")[:2000])
                for o in r.json().get("organic", [])[:k]]


class NewsAPIAdapter(KeyedAdapter):
    name = "newsapi"
    category = SourceCategory.NEWS
    reliability_prior = 0.55
    key_hint = "sources.keys.newsapi (NEWSAPI_KEY) — https://newsapi.org"

    async def _search(self, query: str, k: int) -> list[RawDoc]:
        r = await self.client.get(
            "https://newsapi.org/v2/everything",
            params={"q": query, "pageSize": k, "sortBy": "relevancy",
                    "apiKey": self.api_key})
        r.raise_for_status()
        return [RawDoc(url=a.get("url", ""), title=a.get("title", ""),
                       source=self.name, category=self.category,
                       text=(a.get("description") or "")[:2000],
                       authors=[a.get("author") or ""],
                       published=_dt(a.get("publishedAt")),
                       extra={"outlet": (a.get("source") or {}).get("name", "")})
                for a in r.json().get("articles", [])[:k]]


class IEEEAdapter(KeyedAdapter):
    name = "ieee"
    category = SourceCategory.ACADEMIC
    reliability_prior = 0.85
    key_hint = "sources.keys.ieee (IEEE_API_KEY) — https://developer.ieee.org"

    async def _search(self, query: str, k: int) -> list[RawDoc]:
        r = await self.client.get(
            "https://ieeexploreapi.ieee.org/api/v1/search/articles",
            params={"querytext": query, "max_records": k, "apikey": self.api_key})
        r.raise_for_status()
        return [RawDoc(url=a.get("html_url") or a.get("pdf_url", ""),
                       title=a.get("title", ""),
                       source=self.name, category=self.category,
                       text=(a.get("abstract") or "")[:4000],
                       authors=[au.get("full_name", "") for au in
                                (a.get("authors", {}) or {}).get("authors", [])][:8],
                       published=_dt(a.get("publication_date")))
                for a in r.json().get("articles", [])[:k]]


class PatentsViewAdapter(KeyedAdapter):
    name = "patentsview"
    category = SourceCategory.PATENTS
    reliability_prior = 0.85  # primary patent records (USPTO)
    key_hint = "sources.keys.patentsview (PATENTSVIEW_API_KEY) — https://patentsview.org/apis/keyrequest"

    async def _search(self, query: str, k: int) -> list[RawDoc]:
        import json as _json
        r = await self.client.get(
            "https://search.patentsview.org/api/v1/patent/",
            params={"q": _json.dumps({"_text_any": {"patent_title": query}}),
                    "f": _json.dumps(["patent_id", "patent_title", "patent_date", "patent_abstract"]),
                    "o": _json.dumps({"size": k})},
            headers={"X-Api-Key": self.api_key})
        r.raise_for_status()
        return [RawDoc(url=f"https://patents.google.com/patent/US{p.get('patent_id', '')}",
                       title=p.get("patent_title", ""),
                       source=self.name, category=self.category,
                       text=(p.get("patent_abstract") or "")[:4000],
                       published=_dt(p.get("patent_date"), "%Y-%m-%d"))
                for p in r.json().get("patents", [])[:k]]


class KaggleAdapter(KeyedAdapter):
    name = "kaggle"
    category = SourceCategory.DATA
    reliability_prior = 0.55
    key_hint = "sources.keys.kaggle_username + kaggle_key (KAGGLE_USERNAME/KAGGLE_KEY)"

    def __init__(self, client, username: str = "", key: str = ""):
        super().__init__(client, api_key=key if (username and key) else "")
        self.username = username

    async def _search(self, query: str, k: int) -> list[RawDoc]:
        r = await self.client.get(
            "https://www.kaggle.com/api/v1/datasets/list",
            params={"search": query, "pageSize": k},
            auth=(self.username, self.api_key))
        r.raise_for_status()
        return [RawDoc(url=f"https://www.kaggle.com/datasets/{d.get('ref', '')}",
                       title=d.get("title", ""),
                       source=self.name, category=self.category,
                       text=(d.get("subtitle") or "")[:2000],
                       published=_dt(d.get("lastUpdated")),
                       extra={"downloads": d.get("downloadCount", 0)})
                for d in r.json()[:k]]


class WIPOAdapter(SourceAdapter):
    """Honest stub: WIPO PATENTSCOPE has no practical free programmatic API.

    Exists so the status table states that fact instead of the source
    silently not appearing. International patent coverage flows through
    PatentsView (US) once keyed; WIPO coverage would need their paid feed.
    """
    name = "wipo"
    category = SourceCategory.PATENTS
    reliability_prior = 0.85

    def __init__(self, client):
        super().__init__(client)
        self.status = SourceStatus.NEEDS_KEY
        self.status_detail = "no free API exists; requires WIPO commercial data feed"

    async def _search(self, query: str, k: int) -> list[RawDoc]:
        return []
