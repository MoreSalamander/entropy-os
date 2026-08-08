"""News sources.

GDELT 2.0 DOC API is the keyless workhorse: global news monitoring, free,
no signup. NewsAPI lives in keyed.py for headline coverage once a key exists.
"""

from __future__ import annotations

from datetime import UTC, datetime

from ..models import RawDoc, SourceCategory
from .base import SourceAdapter


class GDELTAdapter(SourceAdapter):
    name = "gdelt_news"
    category = SourceCategory.NEWS
    reliability_prior = 0.5   # raw press: broad but unvetted
    min_interval_s = 1.0

    async def _search(self, query: str, k: int) -> list[RawDoc]:
        r = await self.client.get(
            "https://api.gdeltproject.org/api/v2/doc/doc",
            params={"query": query, "mode": "ArtList", "maxrecords": k,
                    "format": "json", "sort": "hybridrel"})
        r.raise_for_status()
        # GDELT returns text/plain content-type with JSON body; parse defensively.
        try:
            data = r.json()
        except ValueError:
            return []
        docs = []
        for a in data.get("articles", [])[:k]:
            seen = a.get("seendate", "")  # e.g. 20260807T120000Z
            pub = None
            if len(seen) >= 8:
                try:
                    pub = datetime.strptime(seen[:8], "%Y%m%d").replace(tzinfo=UTC)
                except ValueError:
                    pub = None
            docs.append(RawDoc(
                url=a.get("url", ""),
                title=a.get("title", ""),
                source=self.name, category=self.category,
                text=a.get("title", ""),
                published=pub,
                extra={"outlet": a.get("domain", ""), "language": a.get("language", "")},
            ))
        return docs
