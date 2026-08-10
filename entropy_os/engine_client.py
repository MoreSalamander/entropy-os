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


def describe_location() -> str:
    """Where the composite runs, in terms a reader can actually evaluate.

    `http://127.0.0.1:9100` is accurate and useless to a visitor — on a hosted
    page it looks like their own laptop. What matters is whose machine it is.
    """
    url = base_url()
    loopback = "127.0.0.1" in url or "localhost" in url
    if not loopback:
        return url
    host = os.environ.get("FLY_APP_NAME", "")
    if host:
        return f"in this server ({host}), alongside the front door"
    return "on this machine, alongside the front door"


def _down(reason: str) -> dict[str, Any]:
    """The honest empty answer. Callers render the reason rather than a blank."""
    return {"reachable": False, "reason": reason, "url": base_url()}


async def _get(client: httpx.AsyncClient, path: str) -> Any:
    r = await client.get(f"{base_url()}{path}", timeout=TIMEOUT_S)
    r.raise_for_status()
    return r.json()


# A capability that researches a topic or generates a codebase runs for many
# minutes; the eight seconds that suit a health probe would guarantee failure.
EXECUTE_TIMEOUT_S = 1800.0


class EngineUnreachable(RuntimeError):
    """The engine could not be reached at all.

    Distinct on purpose from a capability that ran and failed. The contract
    reserves HTTP errors for transport faults precisely so a caller can tell
    "it refused" from "I never asked it" — collapsing the two would let an
    outage read as a verdict.
    """


async def artifact_text(path: str, rel: str = "") -> dict[str, Any]:
    """Read one file the composition produced, addressed by PATH.

    Distinct from `artifact_file` below, which addresses a file by its place
    in a recorded objective. Both exist because a vend and an objective are
    different things: a vend has a result in hand and no objective record.

    The front door never touches the engines' disk itself. It asks, and the
    engine that owns the artifact decides — which is what keeps this correct
    when the composite stops sharing a filesystem with its members.
    """
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{base_url()}/artifacts/file",
                                 params={"path": path, "rel": rel},
                                 timeout=30.0)
            r.raise_for_status()
            return dict(r.json())
    except (httpx.HTTPError, ValueError) as e:
        raise EngineUnreachable(f"{type(e).__name__}: {e}") from e


async def artifact_tree_at(path: str) -> dict[str, Any]:
    """The files inside an artifact, addressed by path."""
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{base_url()}/artifacts/tree",
                                 params={"path": path}, timeout=30.0)
            r.raise_for_status()
            return dict(r.json())
    except (httpx.HTTPError, ValueError) as e:
        raise EngineUnreachable(f"{type(e).__name__}: {e}") from e


async def run_artifact(path: str, kind: str, description: str = "",
                       objective_id: str = "") -> dict[str, Any]:
    """Build and dispense a disposable copy of one artifact.

    Generous timeout: this builds a container image, which is minutes on a
    cold cache and is exactly the wait a person accepts to see the thing run.
    """
    payload = {"path": path, "kind": kind, "description": description,
               "objective_id": objective_id}
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(f"{base_url()}/artifacts/run", json=payload,
                                  timeout=900.0)
            if r.status_code == 422:
                # A refusal carries a reason worth showing verbatim.
                return {"error": r.json().get("detail", "refused")}
            r.raise_for_status()
            return dict(r.json())
    except (httpx.HTTPError, ValueError) as e:
        raise EngineUnreachable(f"{type(e).__name__}: {e}") from e


async def stop_artifact(container_id: str) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(f"{base_url()}/artifacts/stop",
                                  json={"container_id": container_id},
                                  timeout=60.0)
            r.raise_for_status()
            return dict(r.json())
    except (httpx.HTTPError, ValueError) as e:
        raise EngineUnreachable(f"{type(e).__name__}: {e}") from e


async def execute(capability: str, inputs: dict[str, Any],
                  timeout_s: float = EXECUTE_TIMEOUT_S) -> dict[str, Any]:
    """Run one capability and return the contract's ExecuteResult as a dict.

    Reached through the composite's own /execute, which means a caller names
    a capability and never names an engine. Which member answers — or whether
    a member answers at all rather than a composed pipeline — is the
    composite's business.
    """
    payload = {"capability": capability, "inputs": inputs}
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(f"{base_url()}/execute", json=payload,
                                  timeout=timeout_s)
            r.raise_for_status()
            return dict(r.json())
    except (httpx.HTTPError, ValueError) as e:
        raise EngineUnreachable(f"{type(e).__name__}: {e}") from e


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
        # A loopback URL printed on a hosted page reads as the VISITOR's own
        # machine, which is the opposite of the truth: it means the composite
        # runs inside this same server. Say that instead of showing an address
        # the reader will inevitably mis-attribute.
        "location": describe_location(),
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


# --- the vending path -------------------------------------------------------
# What a run produced, and its contents. Seeing that a composition ran is a
# weaker claim than reading what it made, so these exist to let a visitor open
# the report and browse the generated code rather than take the run on trust.
#
# Every one of these is a READ. one-engine performs the containment check on
# the file route; nothing here widens it, and no path from this side is ever
# handed to the filesystem — it is forwarded to a service that resolves it
# against the artifact root it owns.


async def stock() -> dict[str, Any]:
    """The composed engine's shelf: what it made that can be run."""
    try:
        async with httpx.AsyncClient() as client:
            data = await _get(client, "/artifacts/stock")
    except (httpx.HTTPError, ValueError) as e:
        return _down(f"{type(e).__name__}: {e}")
    return {"reachable": True, **data}


async def artifacts(objective_id: str) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient() as client:
            data = await _get(client, f"/objectives/{objective_id}/artifacts")
    except (httpx.HTTPError, ValueError) as e:
        return _down(f"{type(e).__name__}: {e}")
    return {"reachable": True, **data}


async def artifact_tree(objective_id: str, index: int) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient() as client:
            data = await _get(
                client, f"/objectives/{objective_id}/artifacts/{index}/tree")
    except (httpx.HTTPError, ValueError) as e:
        return _down(f"{type(e).__name__}: {e}")
    return {"reachable": True, **data}


async def artifact_file(objective_id: str, index: int,
                        path: str = "") -> dict[str, Any]:
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"{base_url()}/objectives/{objective_id}/artifacts/{index}/file",
                params={"path": path}, timeout=TIMEOUT_S)
            r.raise_for_status()
            data = r.json()
    except (httpx.HTTPError, ValueError) as e:
        return _down(f"{type(e).__name__}: {e}")
    return {"reachable": True, **data}
