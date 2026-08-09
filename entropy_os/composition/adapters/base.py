"""LeafAdapter — common machinery for wrapping one specialized engine behind
the Universal Engine Contract.

An adapter's whole job is translation: contract capability in → the engine's
existing front door → contract result out, with semantic events, verdicts and
provenance collected along the way. Adapters still call their engine through
its own public entry point and never reach inside it; what changed when the
engines were absorbed is only that the import resolves in this environment
instead of a separate one.
"""

from __future__ import annotations

import asyncio
import importlib.util
import os
import traceback
from collections import deque
from collections.abc import Callable
from pathlib import Path

from ...paths import engine_storage
from ..contract import (
    ArtifactNotServed,
    ArtifactRef,
    CapabilitySpec,
    CompositionNode,
    ContextDescriptor,
    Determinism,
    EngineIdentity,
    EngineManifest,
    ExecuteRequest,
    ExecuteResult,
    HealthReport,
    KnowledgeDescriptor,
    Provenance,
    SemanticEvent,
    StateSnapshot,
    Verdict,
    now_iso,
)

# emit(kind, subject, **payload) — handed to _run so concrete adapters can
# narrate their engine's real progress as semantic facts.
Emit = Callable[..., SemanticEvent]

# vouch(gate, determinism, passed, evidence, **facts) — handed to _run so an
# adapter can report what its engine CHECKED, at the fidelity the engine
# actually has. Engines have always run these checks; before this seam their
# results collapsed into a single output boolean on the way out.
Vouch = Callable[..., Verdict]

# A read surface, not a download service: enough for a report, a lesson or
# a source file, small enough that no single request can be used to haul
# the host's disk through it.
MAX_INLINE_BYTES = 2_000_000


def _within_any(resolved: Path, roots: list[Path]) -> bool:
    """Containment against several roots. Resolution happens BEFORE this, so
    a symlink or `..` cannot walk out of one root and back in through another
    while still looking contained."""
    for root in roots:
        try:
            resolved.relative_to(Path(root).resolve(strict=True))
            return True
        except (OSError, ValueError):
            continue
    return False


class LeafAdapter:
    """Concrete adapters set the class attributes and implement _run()."""

    name: str = "leaf"
    description: str = ""
    datahub_platform: str = ""
    events_emitted: list[str] = []
    # Which contract member this engine is. It names the engine's storage
    # root, which is the ONLY directory it will serve files out of — see
    # artifact_root() and the /artifacts/file route.
    member_key: str = ""
    # Import path of the wrapped engine, checked by health(). Engines are
    # constructed lazily (they load models and graph stores), so without this
    # an adapter would report "ok" right up until the first execution failed
    # on a missing module — health has to answer "can I actually do the work",
    # not "is my HTTP server running".
    engine_module: str = ""

    def __init__(self):
        # Ring buffer only: durable event history belongs to the unified
        # event log and DataHub, not to each engine process.
        self._events: deque[SemanticEvent] = deque(maxlen=500)
        self._active: set[str] = set()
        self._executions_total = 0
        self._counters: dict[str, int] = {}
        self._lock = asyncio.Lock()

    # ----------------------------------------------------------------- #
    # to implement
    # ----------------------------------------------------------------- #
    def capabilities(self) -> list[CapabilitySpec]:
        raise NotImplementedError

    async def _run(self, req: ExecuteRequest, emit: Emit, vouch: Vouch
                   ) -> tuple[dict, list[ArtifactRef], list[str], list[str]]:
        """Execute one capability. Returns (outputs, artifacts,
        datahub_urns, notes).

        `emit` narrates what is happening; `vouch` records what was CHECKED.
        The two are deliberately separate seams — a progress line is a story
        and a verdict is a claim, and only one of them a consumer is entitled
        to trust.
        """
        raise NotImplementedError

    # ----------------------------------------------------------------- #
    # contract implementation
    # ----------------------------------------------------------------- #
    async def describe(self) -> EngineManifest:
        caps = []
        for c in self.capabilities():
            c.engine = self.name
            caps.append(c)
        return EngineManifest(
            identity=EngineIdentity(
                name=self.name, description=self.description, kind="leaf",
                datahub_platform=self.datahub_platform,
                composition=CompositionNode(name=self.name, kind="leaf",
                                            summary=self.description)),
            capabilities=caps,
            events_emitted=list(self.events_emitted))

    async def execute(self, req: ExecuteRequest) -> ExecuteResult:
        known = {c.name for c in self.capabilities()}
        if req.capability not in known:
            return ExecuteResult(
                status="failed",
                error=f"unknown capability {req.capability!r}; "
                      f"this engine offers {sorted(known)}",
                provenance=Provenance(engine=self.name,
                                      capability=req.capability, ref=req.ref))
        collected: list[SemanticEvent] = []

        def emit(kind: str, subject: str = "", **payload) -> SemanticEvent:
            evt = SemanticEvent(kind=kind, engine=self.name, subject=subject,
                                objective_id=req.ref.objective_id,
                                payload=payload)
            collected.append(evt)
            self._events.append(evt)
            return evt

        verdicts: list[Verdict] = []

        def vouch(gate: str, determinism: Determinism, passed: bool,
                  evidence: str, **facts) -> Verdict:
            v = Verdict(gate=gate, determinism=determinism, passed=passed,
                        evidence=evidence, facts=facts)
            verdicts.append(v)
            return v

        started = now_iso()
        self._active.add(req.ref.execution_id)
        self._executions_total += 1
        try:
            outputs, artifacts, urns, notes = await self._run(req, emit, vouch)
            status, error = "completed", ""
        except Exception:
            outputs, artifacts, urns = {}, [], []
            # Full traceback in notes for the operator; short tail as error.
            tb = traceback.format_exc()
            notes = [tb]
            status, error = "failed", tb.strip().splitlines()[-1]
        finally:
            self._active.discard(req.ref.execution_id)
        self._counters[req.capability] = self._counters.get(req.capability, 0) + 1
        return ExecuteResult(
            status=status, outputs=outputs, artifacts=artifacts,
            events=collected, verdicts=verdicts, error=error,
            provenance=Provenance(engine=self.name, capability=req.capability,
                                  ref=req.ref, started_at=started,
                                  finished_at=now_iso(), datahub_urns=urns,
                                  notes=notes))

    def artifact_roots(self) -> list[Path]:
        """Every directory this engine will serve files from.

        Normally one: the engine's own storage. But a deployment can seed
        historical outputs from somewhere else entirely — the hosted face
        ships real recorded runs whose artifacts sit in an image directory,
        not on the data volume — and those are just as legitimately this
        engine's work. The same env vars that tell artifact resolution where
        to look name the extra roots here, so the two cannot disagree about
        what belongs to whom.

        An empty list means "I do not serve files", which is the honest
        answer for an engine with no storage rather than an invitation to
        fall back to the whole filesystem.
        """
        if not self.member_key:
            return []
        roots = [engine_storage(self.member_key)]
        seeded = os.environ.get(
            f"ONE_ENGINE_ARTIFACTS_{self.member_key.upper()}", "").strip()
        if seeded:
            roots.append(Path(seeded))
        return roots

    def artifact_root(self) -> Path | None:
        """The primary root. Kept for callers that want one directory."""
        roots = self.artifact_roots()
        return roots[0] if roots else None

    async def artifact_file(self, path: str, rel: str = "") -> dict:
        """One file this engine produced, or a refusal.

        `path` arrives from the caller, so it is resolved FIRST — following
        symlinks and `..` — and only then required to sit under this engine's
        root. Doing it the other way round tests a string rather than a
        location, which is how a read surface becomes an arbitrary-file read.
        """
        roots = self.artifact_roots()
        if not roots:
            raise ArtifactNotServed("this engine serves no artifact files")
        target = Path(path)
        # A single-file artifact IS the file. Joining `rel` onto it would
        # build `report.md/report.md`, which is how asking for the only file
        # in an artifact turned into a 404.
        if rel and not target.is_file():
            target = target / rel
        try:
            resolved = target.resolve(strict=True)
        except OSError as exc:
            raise ArtifactNotServed("no such file inside this engine") from exc
        if not _within_any(resolved, roots):
            raise ArtifactNotServed("no such file inside this engine")
        if not resolved.is_file():
            raise ArtifactNotServed("not a file")
        if resolved.stat().st_size > MAX_INLINE_BYTES:
            raise ArtifactNotServed("file too large to serve inline")
        return {"path": str(resolved), "engine": self.name,
                "size": resolved.stat().st_size,
                "text": resolved.read_text(encoding="utf-8", errors="replace")}

    async def artifact_tree(self, path: str) -> dict:
        """What is inside one artifact this engine produced.

        Same containment rule as artifact_file, for the same reason: the
        caller supplies the path. A single-file artifact lists itself, so a
        consumer does not need to know which kind it asked about.
        """
        roots = self.artifact_roots()
        if not roots:
            raise ArtifactNotServed("this engine serves no artifact files")
        try:
            resolved = Path(path).resolve(strict=True)
        except OSError as exc:
            raise ArtifactNotServed("no such artifact inside this engine") from exc
        if not _within_any(resolved, roots):
            raise ArtifactNotServed("no such artifact inside this engine")
        if resolved.is_file():
            return {"root": str(resolved), "engine": self.name,
                    "files": [{"path": resolved.name,
                               "size": resolved.stat().st_size}]}
        files = sorted(
            ({"path": str(f.relative_to(resolved)), "size": f.stat().st_size}
             for f in resolved.rglob("*")
             # Caches and build output are not part of what was MADE, and
             # listing them buries the four files a reader actually wants.
             if f.is_file() and not any(
                 part in {"__pycache__", ".git", ".ruff_cache", ".pytest_cache",
                          "node_modules", ".venv", ".next", ".mypy_cache"}
                 or part.endswith((".pyc", ".pyo"))
                 for part in f.relative_to(resolved).parts)),
            key=lambda d: d["path"])
        return {"root": str(resolved), "engine": self.name, "files": files}

    async def health(self) -> HealthReport:
        checks = {"adapter": "up"}
        status = "ok"
        if self.engine_module:
            try:
                found = importlib.util.find_spec(self.engine_module) is not None
            except (ImportError, ValueError):
                found = False
            checks["engine_module"] = (self.engine_module if found
                                       else f"NOT IMPORTABLE: "
                                            f"{self.engine_module}")
            if not found:
                # The adapter is up but cannot do its job: that is down, not
                # degraded — every execution would fail.
                status = "down"
        return HealthReport(engine=self.name, status=status, checks=checks)

    async def state(self) -> StateSnapshot:
        return StateSnapshot(
            engine=self.name, active_executions=sorted(self._active),
            executions_total=self._executions_total,
            events_total=len(self._events),
            last_event_ts=self._events[-1].ts if self._events else "",
            counters=dict(self._counters))

    async def context(self) -> ContextDescriptor:
        return ContextDescriptor(engine=self.name,
                                 description=self.description)

    async def knowledge(self) -> KnowledgeDescriptor:
        return KnowledgeDescriptor(engine=self.name,
                                   description=self.description,
                                   datahub_platform=self.datahub_platform)

    async def recent_events(self, since_id: str = "") -> list[SemanticEvent]:
        events = list(self._events)
        if since_id:
            for i, e in enumerate(events):
                if e.event_id == since_id:
                    return events[i + 1:]
        return events

    async def ingest_event(self, event: SemanticEvent) -> None:
        # Facts from outside are recorded, never obeyed — an adapter may use
        # them as context in future executions, but nothing here dispatches.
        self._events.append(event)

    async def aclose(self) -> None:
        return None

    # ----------------------------------------------------------------- #
    # helpers for concrete adapters
    # ----------------------------------------------------------------- #
    def dataset_urn(self, name: str, env: str = "PROD") -> str:
        """URN of a dataset in this ENGINE's own DataHub platform — the same
        scheme the engine's own bridge uses, so federation lineage lands on
        datasets the engine actually emitted."""
        return (f"urn:li:dataset:(urn:li:dataPlatform:{self.datahub_platform},"
                f"{name},{env})")
