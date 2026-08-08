"""Government / public-data sources.

data.gov's CKAN API is keyless and covers US federal datasets — the honest
live entry for the spec's Government category. Regulations.gov requires a
key (see keyed.py note on the roadmap).
"""

from __future__ import annotations

from ..models import RawDoc, SourceCategory
from .academic import _dt
from .base import SourceAdapter


class DataGovAdapter(SourceAdapter):
    name = "datagov"
    category = SourceCategory.GOVERNMENT
    reliability_prior = 0.8   # primary government data
    min_interval_s = 1.0

    async def _search(self, query: str, k: int) -> list[RawDoc]:
        r = await self.client.get(
            "https://catalog.data.gov/api/3/action/package_search",
            params={"q": query, "rows": k})
        r.raise_for_status()
        docs = []
        for ds in r.json().get("result", {}).get("results", [])[:k]:
            org = (ds.get("organization") or {}).get("title", "")
            docs.append(RawDoc(
                url=f"https://catalog.data.gov/dataset/{ds.get('name', '')}",
                title=ds.get("title", ""),
                source=self.name, category=self.category,
                text=(ds.get("notes") or "")[:3000],
                authors=[org] if org else [],
                published=_dt(ds.get("metadata_modified")),
                extra={"organization": org},
            ))
        return docs
