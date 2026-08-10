"""Keyless web sources: Wikipedia search + a page fetcher for URL follow-ups.

General web search engines (Brave/Serper) are keyed — see keyed.py. Wikipedia
is the keyless encyclopedic baseline; PageFetcher turns any URL surfaced by
another source into extractable text.
"""

from __future__ import annotations

from bs4 import BeautifulSoup

from ..models import RawDoc, SourceCategory, SourceStatus
from .base import SourceAdapter


class WikipediaAdapter(SourceAdapter):
    name = "wikipedia"
    category = SourceCategory.WEB
    reliability_prior = 0.65  # tertiary source: good map, cite the territory
    min_interval_s = 0.3

    def __init__(self, client, contact: str = ""):
        super().__init__(client)
        if not (contact or "").strip():
            # Wikimedia's robot policy requires a contact in the User-Agent and
            # answers 403 to every request without one. Reusing NEEDS_KEY —
            # the fleet's existing fail-closed state — turns twenty doomed
            # calls into one line in the status table that names the fix.
            #
            # This mattered: a run explaining how an LLM works planned
            # Wikipedia into four of its nine agents, 403'd twenty times, and
            # produced a paper about KV-cache compression instead. The failure
            # was reported honestly and still cost the run, because "error,
            # 403" reads like weather and "disabled, set this" reads like a
            # task.
            self.status = SourceStatus.NEEDS_KEY
            self.status_detail = (
                "disabled: set sources.contact (RESEARCH_CONTACT) to an email "
                "— Wikimedia's robot policy 403s a User-Agent without one")

    async def _search(self, query: str, k: int) -> list[RawDoc]:
        r = await self.client.get(
            "https://en.wikipedia.org/w/api.php",
            params={"action": "query", "list": "search", "srsearch": query,
                    "srlimit": k, "format": "json", "srprop": "snippet|timestamp"})
        r.raise_for_status()
        docs = []
        for hit in r.json().get("query", {}).get("search", [])[:k]:
            title = hit.get("title", "")
            snippet = BeautifulSoup(hit.get("snippet", ""), "html.parser").get_text()
            docs.append(RawDoc(
                url=f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}",
                title=title,
                source=self.name, category=self.category,
                text=snippet[:2000],
            ))
        return docs


class PageFetcher:
    """Fetch an arbitrary URL and reduce it to readable text.

    Not a search adapter — the orchestrator uses it to deepen high-value hits
    (e.g. pull the body of a GDELT headline). Same containment rule: failures
    return None, never raise into the pipeline.
    """

    def __init__(self, client):
        self.client = client

    async def fetch_text(self, url: str, max_chars: int = 6000) -> str | None:
        try:
            r = await self.client.get(url)
            r.raise_for_status()
            if "text/html" not in r.headers.get("content-type", "text/html"):
                return None
            soup = BeautifulSoup(r.text, "html.parser")
            for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
                tag.decompose()
            main = soup.find("article") or soup.find("main") or soup.body
            if main is None:
                return None
            text = " ".join(main.get_text(" ").split())
            return text[:max_chars] if text else None
        except Exception:  # noqa: BLE001 — containment boundary
            return None
