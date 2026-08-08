"""Community discussion sources.

Hacker News (Algolia API, keyless, excellent) and Stack Exchange (keyless
quota) are LIVE. Reddit's official API requires OAuth; the public JSON
endpoints still answer from most IPs, so the adapter runs marked DEGRADED —
honest about its flakiness — and any failure downgrades it further to ERROR
rather than pretending.
"""

from __future__ import annotations

from datetime import UTC, datetime

from ..models import RawDoc, SourceCategory, SourceStatus
from .base import SourceAdapter


def _epoch(ts: float | int | None) -> datetime | None:
    if not ts:
        return None
    return datetime.fromtimestamp(float(ts), tz=UTC)


class HackerNewsAdapter(SourceAdapter):
    name = "hackernews"
    category = SourceCategory.COMMUNITY
    reliability_prior = 0.45  # informed community, still opinion-weighted
    min_interval_s = 0.3

    async def _search(self, query: str, k: int) -> list[RawDoc]:
        r = await self.client.get(
            "https://hn.algolia.com/api/v1/search",
            params={"query": query, "tags": "story", "hitsPerPage": k})
        r.raise_for_status()
        docs = []
        for h in r.json().get("hits", [])[:k]:
            docs.append(RawDoc(
                url=h.get("url") or f"https://news.ycombinator.com/item?id={h.get('objectID')}",
                title=h.get("title") or "",
                source=self.name, category=self.category,
                text=(h.get("story_text") or h.get("title") or "")[:2000],
                authors=[h.get("author", "")],
                published=_epoch(h.get("created_at_i")),
                extra={"points": h.get("points", 0), "comments": h.get("num_comments", 0)},
            ))
        return docs


class StackExchangeAdapter(SourceAdapter):
    name = "stackexchange"
    category = SourceCategory.COMMUNITY
    reliability_prior = 0.5
    min_interval_s = 1.0

    async def _search(self, query: str, k: int) -> list[RawDoc]:
        r = await self.client.get(
            "https://api.stackexchange.com/2.3/search/advanced",
            params={"q": query, "site": "stackoverflow", "order": "desc",
                    "sort": "relevance", "pagesize": k})
        r.raise_for_status()
        docs = []
        for q in r.json().get("items", [])[:k]:
            docs.append(RawDoc(
                url=q.get("link", ""),
                title=q.get("title", ""),
                source=self.name, category=self.category,
                text=q.get("title", ""),
                published=_epoch(q.get("creation_date")),
                extra={"score": q.get("score", 0),
                       "answered": q.get("is_answered", False)},
            ))
        return docs


class RedditAdapter(SourceAdapter):
    name = "reddit"
    category = SourceCategory.COMMUNITY
    reliability_prior = 0.35
    min_interval_s = 2.0
    concurrency = 1

    def __init__(self, client, degraded_ok: bool = True):
        super().__init__(client)
        if degraded_ok:
            self.status = SourceStatus.DEGRADED
            self.status_detail = "public JSON endpoints, no OAuth — works from most IPs, may be blocked"
        else:
            self.status = SourceStatus.NEEDS_KEY
            self.status_detail = "disabled: official API needs OAuth app credentials"

    async def _search(self, query: str, k: int) -> list[RawDoc]:
        r = await self.client.get(
            "https://www.reddit.com/search.json",
            params={"q": query, "limit": k, "sort": "relevance"})
        r.raise_for_status()
        docs = []
        for child in r.json().get("data", {}).get("children", [])[:k]:
            d = child.get("data", {})
            docs.append(RawDoc(
                url=f"https://www.reddit.com{d.get('permalink', '')}",
                title=d.get("title", ""),
                source=self.name, category=self.category,
                text=(d.get("selftext") or d.get("title") or "")[:2000],
                authors=[d.get("author", "")],
                published=_epoch(d.get("created_utc")),
                extra={"score": d.get("score", 0), "subreddit": d.get("subreddit", "")},
            ))
        return docs
