"""The hosted wedge: the narrow path by which someone OTHER than the author runs Entropy OS.

This lives in the front door, not in the engine room. It used to sit in
veritas/products/ because the studios it called lived there too; now that it
calls engines through the Universal Engine Contract, keeping it there would
mean the engine room importing the front door's contract client — the
dependency pointing backwards. What it owns is front-door business anyway:
identity, tenancy, metering, and the refusal to run without isolation. None
of that is an engine's concern, and an engine must never be trusted to
enforce it.

A stranger submits a goal; the work runs ISOLATED (the sandboxed executor),
PERSISTED (a per-tenant memory), and GATED (the same verification model the author uses).
The wedge adds exactly the three things a single-user local hub never needed:

  • an IDENTITY — a bearer token maps to a tenant id, so a run is attributable;
  • per-tenant ISOLATION — each tenant's memory lives at its own path, so one tenant can never read
    another's lessons or artifacts;
  • a FAIL-CLOSED guard — if the execution sandbox is not actually active, the run is REFUSED, never
    silently executed on the host. No isolation ⇒ no run. That is the load-bearing safety property.

"Minimal auth" here is the floor that PROVES isolation, not a product: a static token→tenant table.
Real accounts, sessions, rate limits, and billing are P31c2 — none of them change whether the
architecture holds. This module is pure logic (no web framework) so it is unit-testable; the HTTP
endpoints in hub/app.py are a thin shell over `Wedge.submit`.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from commons.parallel_client import SearchClient
from engine.executor import sandbox_active
from engine.memory import MemoryStore, default_memory_store
from engine.model import ModelProvider

from . import engine_client
from .composition.contract import Verdict
from .vending import SLOT_CAPABILITY, SLOT_INPUT_FIELD, decide

# A tenant id becomes a directory name, so it must be path-safe by construction (no separators, no
# traversal). Tokens are operator-defined, but we validate anyway — defense in depth.
_TENANT_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


def new_run_token() -> str:
    return uuid.uuid4().hex[:12]


def tenant_slug(name: str) -> str:
    """A tenant id safe to hand an engine as a learner name."""
    return re.sub(r"[^a-z0-9_-]", "-", name.lower())[:64] or "tenant"


def _default_execute(capability: str, inputs: dict[str, Any]) -> dict[str, Any]:
    """Reach the real composite. Separated so the seam has a name."""
    return run_sync(engine_client.execute(capability, inputs))


def _default_read_artifact(path: str) -> dict[str, Any]:
    return run_sync(engine_client.artifact_text(path))


def run_sync(coro: Any) -> Any:
    """Run one contract call from this synchronous module.

    The wedge is deliberately framework-free and is called from FastAPI's
    threadpool and from background worker threads — never from inside a
    running loop. asyncio.run is therefore correct here, and the explicit
    check turns a subtle "this coroutine was never awaited" into a loud
    error if that ever stops being true.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    raise RuntimeError(
        "wedge.run_sync was called from inside an event loop; the caller "
        "should await the contract client directly")


class Unauthorized(Exception):
    """Missing or unrecognized bearer token — the request has no tenant identity."""


class SourcesUnavailable(Exception):
    """The research slot was asked to research with no live-search client and
    no pasted sources — refused honestly rather than degraded into a
    hallucination engine."""


class OrgNotVendable(Exception):
    """The requested slot isn't on the machine. Deterministic allowlist — a
    stranger can only run the orgs the operator chose to vend."""


# The made-to-order slots: looks right (web), cited right (research), runs
# right (software) — and site: a whole website, looks right TOGETHER (the
# design agency: brief, design corpus, synthesis with provenance, one wall
# per page, site gates across them). Everything else stays operator-only.
VENDABLE_ORGS = ("software", "web", "research", "site", "learn")


class SandboxUnavailable(Exception):
    """Isolation is not active, so an untrusted run must NOT proceed. The wedge fails closed."""


class QuotaExceeded(Exception):
    """The tenant has spent its allowance for the current window — the run is refused (HTTP 429)."""


@runtime_checkable
class Meter(Protocol):
    """The metering seam: count a tenant's runs, enforce a ceiling, and report what's left. The same
    ledger a billing system reads. Optional — a local wedge runs without one (unlimited)."""

    def check(self, tenant: str) -> None: ...        # raise QuotaExceeded if over the limit
    def record(self, tenant: str, accepted: bool, goal: str) -> None: ...
    def remaining(self, tenant: str) -> int: ...


@runtime_checkable
class Authenticator(Protocol):
    """The auth seam: turn an `Authorization` header into a tenant id, or raise `Unauthorized`. The
    static `WedgeAuth` (env tokens, P31c1) and the DB-backed `AccountStore` (real accounts, P31c2)
    are interchangeable behind it — the wedge never learns which one it holds."""

    def tenant_for(self, authorization: str | None) -> str: ...


def parse_bearer(authorization: str | None) -> str | None:
    """Pull the raw token out of an `Authorization: Bearer <token>` header (or accept a bare token).
    Shared so every authenticator strips the scheme the same way."""
    if not authorization:
        return None
    header = authorization.strip()
    return header[7:].strip() if header[:7].lower() == "bearer " else header


@dataclass(frozen=True)
class WedgeAuth:
    """A static bearer-token → tenant-id table. The minimal identity floor (P31c1)."""

    tokens: dict[str, str]

    @classmethod
    def from_env(cls, raw: str | None = None) -> WedgeAuth:
        """Parse VERITAS_WEDGE_TOKENS='tok_a:alice,tok_b:bob'. An EMPTY table means the wedge is
        closed — every request is Unauthorized — which is the safe default for an unconfigured host."""
        raw = raw if raw is not None else os.environ.get("VERITAS_WEDGE_TOKENS", "")
        tokens: dict[str, str] = {}
        for pair in raw.split(","):
            token, _, tenant = pair.strip().partition(":")
            token, tenant = token.strip(), tenant.strip()
            if token and tenant and _TENANT_RE.match(tenant):
                tokens[token] = tenant
        return cls(tokens)

    def tenant_for(self, authorization: str | None) -> str:
        """Map an `Authorization: Bearer <token>` header (or a bare token) to a tenant id, or refuse."""
        token = parse_bearer(authorization)
        if not token:
            raise Unauthorized("missing Authorization header")
        tenant = self.tokens.get(token)
        if not tenant:
            raise Unauthorized("unrecognized token")
        return tenant


@dataclass
class WedgeResult:
    tenant: str
    goal: str
    accepted: bool
    run_id: str
    isolated: bool          # the run executed inside the sandbox
    # the tenant's data root — for the operator's audit, never another tenant's
    persisted_at: str
    code: str = ""          # the function the org built (the actual deliverable, shown on SHIPPED)
    # the contract extracted from the goal BEFORE any code — the "why"
    spec: dict[str, Any] | None = None
    # the gate verdicts behind the decision
    evidence: list[dict[str, Any]] = field(default_factory=list)
    remaining: int | None = None  # runs left in the tenant's window, when a meter is attached
    org: str = "software"   # which slot vended this
    artifacts: list[dict[str, Any]] = field(default_factory=list)  # what dropped into the tray


def _evidence(result: Any) -> list[dict[str, Any]]:
    """The gate trail behind the decision — what was checked and how it fell. This is the wedge's
    honesty: the stranger sees not just accept/reject but the deterministic gates that decided it."""
    outcome = getattr(result, "code_outcome", None) or getattr(result, "spec_outcome", None)
    if outcome is None:
        return []
    return [
        {
            "gate": gr.gate_name,
            "determinism": gr.determinism.value,
            "passed": gr.passed,
            "evidence": gr.evidence,
        }
        for gr in outcome.gate_results
    ]


class Wedge:
    """The hosted submission service. `submit` is the whole public surface."""

    def __init__(
        self,
        base: Path | str,
        provider_factory: Callable[[], ModelProvider],
        auth: Authenticator,
        *,
        sandbox_check: Callable[[], bool] = sandbox_active,
        memory_factory: Callable[[Path], MemoryStore] = default_memory_store,
        meter: Meter | None = None,
        unlimited_check: Callable[[str], bool] | None = None,
        search_client: SearchClient | None = None,
        execute: Callable[[str, dict[str, Any]], dict[str, Any]] | None = None,
        read_artifact: Callable[[str], dict[str, Any]] | None = None,
    ) -> None:
        self.base = Path(base)
        self.provider_factory = provider_factory
        self.auth = auth
        # Injectable so tests can assert the fail-closed contract without a Docker daemon, and so a
        # future executor-injection can tighten the promise. Default is the live sandbox check.
        self.sandbox_check = sandbox_check
        self.memory_factory = memory_factory
        self.meter = meter  # None => unlimited (local); a QuotaStore => metered (hosted)
        # Returns True for tenants exempt from the quota (owner / unlimited accounts) — they skip the meter.
        self.unlimited_check = unlimited_check
        # The live-research seam: when set, the research slot with no pasted
        # sources FETCHES its own corpus (machine-fetched tier). Without it,
        # empty-sources research is refused — a report grounded in nothing
        # would be a summarizer wearing a lab coat.
        self.search_client = search_client
        # The contract seam. Injectable for the same reason the model provider
        # always was: a unit test must be able to exercise this logic without
        # a live engine on the other end. The default reaches the real
        # composite; a test hands in a function and asserts on what the wedge
        # DID with the result, which is the part that is actually its own.
        self._execute = execute or _default_execute
        self._read_artifact = read_artifact or _default_read_artifact

    def tenant_root(self, tenant: str) -> Path:
        if not _TENANT_RE.match(tenant):  # defense in depth; the token table already validated it
            raise Unauthorized("invalid tenant id")
        return self.base / "tenants" / tenant

    def submit(
        self, *, authorization: str | None, goal: str,
        org: str = "software", sources: list[str] | None = None,
    ) -> WedgeResult:
        """Authenticate → verify isolation is live → run the chosen slot's org in the tenant's own memory.

        Order matters: identity first (no anonymous runs), the slot allowlist and sandbox guard SECOND
        and BEFORE any model-authored code can execute (fail closed), the gated build last. The sandbox
        guard applies to every slot — web and research don't execute stranger code the way software
        does, but one uniform floor is simpler to trust than three special cases."""
        tenant = self.auth.tenant_for(authorization)            # Unauthorized on a bad/absent token
        if org not in VENDABLE_ORGS:
            raise OrgNotVendable(f"slot {org!r} is not on this machine (offered: "
                f"{', '.join(VENDABLE_ORGS)})")
        if not self.sandbox_check():                            # FAIL CLOSED — no isolation, no run
            raise SandboxUnavailable(
                "execution sandbox is not active; refusing to run untrusted code on the host"
            )
        # owner / unlimited
        exempt = self.unlimited_check is not None and self.unlimited_check(tenant)
        if self.meter is not None and not exempt:
            # QuotaExceeded if over the window's limit
            self.meter.check(tenant)
        root = self.tenant_root(tenant)
        # The tenant's own directory is the isolation boundary and the
        # operator's audit trail, so it exists because a run happened here —
        # not as a side effect of something else having written to it.
        root.mkdir(parents=True, exist_ok=True)
        return self._submit_via_contract(tenant, goal, org, root, exempt)

    # ----------------------------------------------------------------- #
    # the contract path
    # ----------------------------------------------------------------- #

    def _tenant_inputs(self, org: str, goal: str, root: Path) -> dict[str, Any]:
        """The capability's inputs, scoped to this tenant where it can be.

        Tenancy is the wedge's promise, not the engines' — they were built to
        serve one operator and have no notion of who is asking. Two
        capabilities can be scoped today and are:

          software.build       out_dir      → this tenant's own directory
          university.design…   learner_name → this tenant's own learner profile

        research.investigate and web.generate_site take no scope, so their
        runs share one knowledge graph and one output directory across every
        tenant. Artifacts are still only handed back to the tenant whose run
        produced them — the wedge never returns a path it did not just get —
        but accumulated KNOWLEDGE is shared, which means one tenant's research
        can inform another's. That is a real narrowing of the isolation
        promise, it is recorded here rather than papered over, and it is the
        remaining blocker for multi-tenant hosting of those two slots.
        """
        field = SLOT_INPUT_FIELD[org]
        inputs: dict[str, Any] = {field: goal}
        if org == "software":
            inputs["out_dir"] = str(root / "software" / f"build-{new_run_token()}")
        elif org == "learn":
            inputs["learner_name"] = tenant_slug(root.name)
        return inputs

    def _submit_via_contract(
        self, tenant: str, goal: str, org: str, root: Path, exempt: bool,
    ) -> WedgeResult:
        """Run one slot through the Universal Engine Contract.

        The wedge no longer knows how any of this is built. It knows which
        capability serves the slot, what the engine reported checking, and the
        one rule that turns those verdicts into a decision.
        """
        capability = SLOT_CAPABILITY[org]
        try:
            result = self._execute(capability,
                                   self._tenant_inputs(org, goal, root))
        except engine_client.EngineUnreachable as exc:
            # Unreachable is not rejected. Charging for a vend that never ran,
            # or showing "not accepted" for a machine that was simply down,
            # would both be lies of different kinds.
            raise SourcesUnavailable(
                f"the {org} engine is not reachable right now: {exc}") from exc

        verdicts = [Verdict.model_validate(v) for v in result.get("verdicts", [])]
        decision = decide(result.get("status", "failed"), verdicts,
                          result.get("error", ""))
        artifacts = self._collect_artifacts(org, result)

        remaining: int | None = None
        if self.meter is not None and not exempt:
            self.meter.record(tenant, decision.accepted, goal)
            remaining = self.meter.remaining(tenant)
        elif exempt:
            remaining = -1

        outputs = result.get("outputs") or {}
        return WedgeResult(
            tenant=tenant,
            goal=goal,
            accepted=decision.accepted,
            run_id=(result.get("provenance") or {}).get("ref", {}).get(
                "execution_id", "") or new_run_token(),
            isolated=True,
            persisted_at=str(root),
            code=next((a["payload"] for a in artifacts
                       if a["label"] == "generated code"), ""),
            spec=outputs if isinstance(outputs, dict) else None,
            evidence=decision.verdicts,
            remaining=remaining,
            org=org,
            artifacts=artifacts,
        )

    def _collect_artifacts(self, org: str, result: dict[str, Any]) -> list[dict[str, Any]]:
        """What dropped into the tray.

        A single-file artifact is fetched and shown. A directory is named,
        measured and left as a reference — inlining a whole generated project
        would flood the page, and pretending a tree is a document would be
        worse. The reason each entry looks the way it does is stated, so a
        visitor is never left guessing whether something is missing.
        """
        artifacts: list[dict[str, Any]] = []
        outputs = result.get("outputs") or {}

        # The report a research run wrote is the deliverable, and it is one
        # file, so it is fetched rather than referenced.
        report_path = outputs.get("report_path")
        if report_path:
            try:
                got = self._read_artifact(str(report_path))
                artifacts.append({"label": "grounded report",
                                  "payload": got.get("text", "")})
            except engine_client.EngineUnreachable:
                pass

        for ref in result.get("artifacts") or []:
            kind = ref.get("kind", "artifact")
            path = ref.get("path", "")
            if not path or (report_path and path == report_path):
                continue
            try:
                got = self._read_artifact(path)
                label = "generated code" if kind in ("project", "sidecar") else kind
                artifacts.append({"label": label, "payload": got.get("text", "")})
            except engine_client.EngineUnreachable:
                # A directory, or an engine that will not serve it. Name it
                # honestly instead of dropping it silently.
                artifacts.append({
                    "label": f"{kind} (directory)",
                    "payload": f"{ref.get('description', kind)}\n{path}",
                })
        return artifacts

    def grade_learn(self, authorization: str | None, run_id: str,
                    answers: list[int]) -> dict[str, Any]:
        """The assessment door: deterministic grading, and the only way the
        learner model moves. Never metered — grading is part of the vend, not
        a second purchase.

        The grading itself belongs to the university engine, which owns the
        answer key and the mastery rules; the wedge's job is to remember which
        session belongs to which tenant, so one learner can never grade
        against another's activity. That bookkeeping is the isolation, and it
        stays here where tenancy is understood.
        """
        tenant = self.auth.tenant_for(authorization)
        root = self.base / "tenants" / tenant
        memory = self.memory_factory(root / "learn")

        pending = None
        for record in memory.load_all():
            if (record.category == "artifact"
                    and record.title == f"pending-quiz:{run_id}"):
                pending = record
                break
        if pending is None:
            raise KeyError(f"no gradable lesson for run {run_id!r} in this tenant")
        data = json.loads(pending.body)

        result = self._execute("university.assess", {
            "session_id": data["session_id"],
            "activity_id": data["activity_id"],
            "answers": {str(i): a for i, a in enumerate(answers)},
        })
        if result.get("status") != "completed":
            raise SourcesUnavailable(
                f"grading did not complete: {result.get('error', 'unknown')}")
        outputs = result.get("outputs") or {}
        graded = outputs.get("graded") or []
        return {
            "concept": data.get("concept", ""),
            "correct": sum(1 for g in graded if g.get("correct")),
            "total": len(graded),
            "mastery": outputs.get("mastery_level", ""),
            "graded": graded,
        }
