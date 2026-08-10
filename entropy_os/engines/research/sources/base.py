"""Source adapter contract.

Every information source — academic index, code host, news firehose, patent
office — implements this one interface. The orchestrator treats them
uniformly, which is what makes the parallel fan-out and the honest status
table possible.

Adapter obligations:
  * declare category + reliability_prior (deterministic scoring input)
  * respect its own politeness: per-adapter concurrency gate + min interval
  * NEVER raise out of search(): failures return [] and set status=ERROR
    with the reason recorded — a broken source degrades the run, it does
    not kill it. The registry surfaces every degradation in the report.
"""

from __future__ import annotations

import asyncio
import time
from abc import ABC, abstractmethod

import httpx

from ..models import RawDoc, SourceCategory, SourceStatus

# The identity this fleet presents to every source it calls.
#
# The contact is not decoration. Wikimedia's robot policy rejects a User-Agent
# whose contact is a URL — 403 Forbidden, every call, with the policy link in
# the body — and Crossref sorts requests carrying a mailto into a "polite pool"
# with far higher rate limits than the anonymous one. A run against a fleet of
# public APIs is a guest on other people's infrastructure, and this string is
# how it introduces itself.
#
# It is empty by default because it is a *personal* detail: this repository is
# public, and an address committed here is an address in a crawler's index.
# Operators set `sources.contact` in research.yaml or RESEARCH_CONTACT in the
# environment; a clone with neither still runs, with the sources that demand a
# contact honestly disabled rather than silently failing.
_UA_BASE = "research-engine/0.1 (MoreSalamander; research aggregation"


def user_agent(contact: str = "") -> str:
    contact = (contact or "").strip()
    tail = f"; contact: {contact}" if contact else "; no contact configured"
    return f"{_UA_BASE}{tail})"


# The no-contact form, kept as a module constant for the three sibling engines
# that do their own light fetching and have no research config to read.
USER_AGENT = user_agent()


class SourceAdapter(ABC):
    name: str = "base"
    category: SourceCategory = SourceCategory.WEB
    reliability_prior: float = 0.5   # 0..1, how much this source is trusted a priori
    min_interval_s: float = 0.5      # politeness floor between calls
    concurrency: int = 3

    def __init__(self, client: httpx.AsyncClient):
        self.client = client
        self.status: SourceStatus = SourceStatus.LIVE
        self.status_detail: str = ""
        self._sem = asyncio.Semaphore(self.concurrency)
        self._last_call = 0.0
        self._lock = asyncio.Lock()
        self.calls = 0
        self.docs_returned = 0

    # -- politeness -------------------------------------------------------
    async def _throttle(self) -> None:
        async with self._lock:
            wait = self.min_interval_s - (time.monotonic() - self._last_call)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_call = time.monotonic()

    # -- public entry point ----------------------------------------------
    async def search(self, query: str, k: int) -> list[RawDoc]:
        """Rate-limited, failure-contained search. Orchestrator calls only this."""
        if self.status == SourceStatus.NEEDS_KEY:
            return []  # fail-closed: disabled adapters contribute nothing silently-wrong
        async with self._sem:
            await self._throttle()
            self.calls += 1
            try:
                docs = await self._search(query, k)
                self.docs_returned += len(docs)
                return docs
            except Exception as e:  # noqa: BLE001 — containment boundary by design
                self.status = SourceStatus.ERROR
                self.status_detail = f"{type(e).__name__}: {e}"[:200]
                return []

    @abstractmethod
    async def _search(self, query: str, k: int) -> list[RawDoc]:
        """Source-specific implementation. May raise; search() contains it."""

    # -- introspection ----------------------------------------------------
    def status_row(self) -> dict:
        return {
            "source": self.name,
            "category": self.category.value,
            "status": self.status.value,
            "detail": self.status_detail,
            "reliability_prior": self.reliability_prior,
            "calls": self.calls,
            "docs": self.docs_returned,
        }


class KeyedAdapter(SourceAdapter):
    """Base for adapters that need an API key. Missing key => NEEDS_KEY status,
    same interface, zero silent behavior. Paste the key in config.yaml (or env)
    and the adapter goes live with no code changes."""

    key_hint: str = ""  # which config field / signup URL unlocks this source

    def __init__(self, client: httpx.AsyncClient, api_key: str = ""):
        super().__init__(client)
        self.api_key = api_key
        if not api_key:
            self.status = SourceStatus.NEEDS_KEY
            self.status_detail = f"disabled: set {self.key_hint}"
