"""Code and model-hub sources — live keyless.

GitHub search runs unauthenticated (60 req/hr ceiling — set GITHUB_TOKEN in
the environment and the adapter picks it up for 5000/hr). GitLab and
Hugging Face public APIs are keyless.
"""

from __future__ import annotations

import os

from ..models import RawDoc, SourceCategory
from .academic import _dt
from .base import SourceAdapter


class GitHubAdapter(SourceAdapter):
    name = "github"
    category = SourceCategory.CODE
    reliability_prior = 0.6
    min_interval_s = 2.0      # unauthenticated search is tightly limited
    concurrency = 1

    async def _search(self, query: str, k: int) -> list[RawDoc]:
        headers = {"Accept": "application/vnd.github+json"}
        token = os.environ.get("GITHUB_TOKEN", "")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        r = await self.client.get(
            "https://api.github.com/search/repositories",
            params={"q": query, "sort": "stars", "per_page": k}, headers=headers)
        r.raise_for_status()
        docs = []
        for repo in r.json().get("items", [])[:k]:
            docs.append(RawDoc(
                url=repo.get("html_url", ""),
                title=repo.get("full_name", ""),
                source=self.name, category=self.category,
                text=(repo.get("description") or "")[:2000],
                published=_dt(repo.get("updated_at")),
                extra={"stars": repo.get("stargazers_count", 0),
                       "language": repo.get("language")},
            ))
        return docs


class GitLabAdapter(SourceAdapter):
    name = "gitlab"
    category = SourceCategory.CODE
    reliability_prior = 0.55
    min_interval_s = 1.0

    async def _search(self, query: str, k: int) -> list[RawDoc]:
        r = await self.client.get(
            "https://gitlab.com/api/v4/projects",
            params={"search": query, "order_by": "star_count", "per_page": k})
        r.raise_for_status()
        docs = []
        for p in r.json()[:k]:
            docs.append(RawDoc(
                url=p.get("web_url", ""),
                title=p.get("path_with_namespace", ""),
                source=self.name, category=self.category,
                text=(p.get("description") or "")[:2000],
                published=_dt(p.get("last_activity_at")),
                extra={"stars": p.get("star_count", 0)},
            ))
        return docs


class HuggingFaceAdapter(SourceAdapter):
    name = "huggingface"
    category = SourceCategory.DATA
    reliability_prior = 0.6
    min_interval_s = 0.5

    async def _search(self, query: str, k: int) -> list[RawDoc]:
        docs: list[RawDoc] = []
        # Models and datasets both matter for research topics; split the budget.
        for kind in ("models", "datasets"):
            r = await self.client.get(
                f"https://huggingface.co/api/{kind}",
                params={"search": query, "limit": max(k // 2, 2), "sort": "downloads"})
            r.raise_for_status()
            for item in r.json():
                item_id = item.get("id", "")
                docs.append(RawDoc(
                    url=f"https://huggingface.co/{'datasets/' if kind == 'datasets' else ''}{item_id}",
                    title=item_id,
                    source=self.name, category=self.category,
                    text=f"{kind[:-1]} on Hugging Face; downloads={item.get('downloads', 0)}",
                    published=_dt(item.get("lastModified")),
                    extra={"downloads": item.get("downloads", 0), "kind": kind[:-1]},
                ))
        return docs[:k]
