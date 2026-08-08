"""Entropy OS as a consumer of the Universal Engine Contract.

one-engine composes four specialized engines — research, university, software,
web — and exposes the *same* contract it consumes. That is the property worth
using rather than describing: Entropy OS talks to it over HTTP exactly the way
it talks to any single engine, and never learns that four engines are inside.

So this module is deliberately thin. It is not an integration layer that knows
one-engine's internals; it is a client for a contract. If one-engine were
replaced tomorrow by a single engine, or by a composite of twelve, nothing here
would change — which is the whole claim being made, made checkable.

**It degrades honestly.** one-engine runs as its own service; when it is not
reachable, every call here returns a reachable=False envelope carrying the
reason. Nothing is cached, invented, or served from a snapshot: a wing that
showed stale runs while the system was down would be worse than a wing that
says the system is down.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

# Where the composite lives. Locally that is the laptop's own :9100; on the
# hosted face it is whatever ONE_ENGINE_URL names — the contract is addressed
# by URL precisely so moving it is a configuration change and nothing else.
DEFAULT_URL = "http://localhost:9100"
TIMEOUT_S = 8.0


def base_url() -> str:
    return os.environ.get("ONE_ENGINE_URL", DEFAULT_URL).rstrip("/")


def _down(reason: str) -> dict[str, Any]:
    """The honest empty answer. Callers render the reason rather than a blank."""
    return {"reachable": False, "reason": reason, "url": base_url()}


async def _get(client: httpx.AsyncClient, path: str) -> Any:
    r = await client.get(f"{base_url()}{path}", timeout=TIMEOUT_S)
    r.raise_for_status()
    return r.json()


async def overview() -> dict[str, Any]:
    """Identity, capabilities, composition tree and health, in one round trip.

    All four come from the contract's own routes — nothing is assembled from
    knowledge of what one-engine happens to contain.
    """
    try:
        async with httpx.AsyncClient() as client:
            composition = await _get(client, "/composition")
            health = await _get(client, "/health")
    except (httpx.HTTPError, ValueError) as e:
        return _down(f"{type(e).__name__}: {e}")

    identity = composition.get("identity", {})
    return {
        "reachable": True,
        "url": base_url(),
        "contract_version": composition.get("contract_version", ""),
        "identity": identity,
        "composition": identity.get("composition", {}),
        "capabilities": composition.get("capabilities", []),
        "pipelines": composition.get("composed_pipelines", {}),
        "health": health,
    }


async def objectives() -> dict[str, Any]:
    """Real composed runs, newest first.

    These are runs that actually happened — including the ones that failed.
    A composed run that stops partway is still a run, and hiding it would
    defeat the point of publishing provenance at all.
    """
    try:
        async with httpx.AsyncClient() as client:
            listing = await _get(client, "/objectives")
    except (httpx.HTTPError, ValueError) as e:
        return _down(f"{type(e).__name__}: {e}")

    items = listing if isinstance(listing, list) else listing.get("objectives", [])
    return {"reachable": True, "url": base_url(), "objectives": items}


async def objective(objective_id: str) -> dict[str, Any]:
    """One run in full: stages, gate verdicts, artifacts, provenance."""
    try:
        async with httpx.AsyncClient() as client:
            detail = await _get(client, f"/objectives/{objective_id}")
    except (httpx.HTTPError, ValueError) as e:
        return _down(f"{type(e).__name__}: {e}")
    return {"reachable": True, "url": base_url(), "objective": detail}
