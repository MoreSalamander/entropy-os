"""Adapter registry: builds the full source fleet and reports its health.

The registry is the honesty mechanism for sources — `status_table()` goes
straight into the final report so a reader always knows which sources were
live, which were degraded, and which sat out for lack of a key.
"""

from __future__ import annotations

import httpx

from ..config import Config
from .base import USER_AGENT, SourceAdapter
from .academic import ArxivAdapter, CrossrefAdapter, OpenAlexAdapter, PubMedAdapter, SemanticScholarAdapter
from .code import GitHubAdapter, GitLabAdapter, HuggingFaceAdapter
from .community import HackerNewsAdapter, RedditAdapter, StackExchangeAdapter
from .government import DataGovAdapter
from .keyed import (BraveSearchAdapter, IEEEAdapter, KaggleAdapter,
                    NewsAPIAdapter, PatentsViewAdapter, SerperAdapter, WIPOAdapter)
from .news import GDELTAdapter
from .web import WikipediaAdapter


class SourceRegistry:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        # One pooled HTTP client for the whole fleet: connection reuse across
        # hundreds of concurrent tasks instead of per-call sockets.
        self.client = httpx.AsyncClient(
            headers={"User-Agent": USER_AGENT},
            timeout=httpx.Timeout(25.0),
            follow_redirects=True,
            limits=httpx.Limits(max_connections=64, max_keepalive_connections=32),
        )
        keys = cfg.sources.keys
        self.adapters: dict[str, SourceAdapter] = {}
        fleet: list[SourceAdapter] = [
            # -- live keyless ------------------------------------------------
            ArxivAdapter(self.client),
            OpenAlexAdapter(self.client),
            SemanticScholarAdapter(self.client),
            PubMedAdapter(self.client),
            CrossrefAdapter(self.client),
            WikipediaAdapter(self.client),
            GitHubAdapter(self.client),
            GitLabAdapter(self.client),
            HuggingFaceAdapter(self.client),
            HackerNewsAdapter(self.client),
            StackExchangeAdapter(self.client),
            GDELTAdapter(self.client),
            DataGovAdapter(self.client),
            RedditAdapter(self.client, degraded_ok=cfg.sources.reddit_degraded_ok),
            # -- keyed (NEEDS_KEY until configured) --------------------------
            BraveSearchAdapter(self.client, keys.brave_search),
            SerperAdapter(self.client, keys.serper),
            NewsAPIAdapter(self.client, keys.newsapi),
            IEEEAdapter(self.client, keys.ieee),
            PatentsViewAdapter(self.client, keys.patentsview),
            KaggleAdapter(self.client, keys.kaggle_username, keys.kaggle_key),
            WIPOAdapter(self.client),
        ]
        for a in fleet:
            self.adapters[a.name] = a

    def get(self, name: str) -> SourceAdapter | None:
        return self.adapters.get(name)

    def live_names(self) -> list[str]:
        from ..models import SourceStatus
        return [n for n, a in self.adapters.items()
                if a.status in (SourceStatus.LIVE, SourceStatus.DEGRADED)]

    def status_table(self) -> list[dict]:
        return [a.status_row() for a in self.adapters.values()]

    async def aclose(self) -> None:
        await self.client.aclose()
