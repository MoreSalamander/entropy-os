"""LeafAdapter — common machinery for wrapping one specialized engine behind
the Universal Engine Contract.

An adapter's whole job is translation: contract capability in → the engine's
existing front door → contract result out, with semantic events and
provenance collected along the way. Adapters run inside their engine's OWN
venv and never modify the engine — the four repositories stay byte-identical.
"""

from __future__ import annotations

import asyncio
import importlib.util
import traceback
from collections import deque
from typing import Callable

from ..contract import (ArtifactRef, CapabilitySpec, CompositionNode,
                        ContextDescriptor, EngineIdentity, EngineManifest,
                        ExecuteRequest, ExecuteResult, HealthReport,
                        KnowledgeDescriptor, Provenance, SemanticEvent,
                        StateSnapshot, now_iso)

# emit(kind, subject, **payload) — handed to _run so concrete adapters can
# narrate their engine's real progress as semantic facts.
Emit = Callable[..., SemanticEvent]


class LeafAdapter:
    """Concrete adapters set the class attributes and implement _run()."""

    name: str = "leaf"
    description: str = ""
    datahub_platform: str = ""
    events_emitted: list[str] = []
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

    async def _run(self, req: ExecuteRequest, emit: Emit
                   ) -> tuple[dict, list[ArtifactRef], list[str], list[str]]:
        """Execute one capability. Returns (outputs, artifacts,
        datahub_urns, notes)."""
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

        started = now_iso()
        self._active.add(req.ref.execution_id)
        self._executions_total += 1
        try:
            outputs, artifacts, urns, notes = await self._run(req, emit)
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
            events=collected, error=error,
            provenance=Provenance(engine=self.name, capability=req.capability,
                                  ref=req.ref, started_at=started,
                                  finished_at=now_iso(), datahub_urns=urns,
                                  notes=notes))

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
