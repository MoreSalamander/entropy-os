"""The engine protocol — the behavioral half of the Universal Engine Contract.

Anything implementing ComposableEngine can be composed: a leaf adapter
wrapping one specialized engine, a RemoteEngine proxying a contract server
over HTTP, or a CompositeEngine wrapping many members. Callers cannot tell
these apart, and must never need to — that indistinguishability is what makes
ENGINE → SYSTEM → CAPABILITY recursion real rather than rhetorical.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .schema import (ContextDescriptor, EngineManifest, ExecuteRequest,
                     ExecuteResult, HealthReport, KnowledgeDescriptor,
                     SemanticEvent, StateSnapshot)


@runtime_checkable
class ComposableEngine(Protocol):
    """The complete surface a composed system relies on. Every method maps
    1:1 onto an HTTP route in contract.http, so local and remote engines are
    interchangeable by construction."""

    async def describe(self) -> EngineManifest:
        """Identity + capabilities + events + workflows. Self-description is
        the contract's answer to 'what are you and what can you do?'"""
        ...

    async def execute(self, req: ExecuteRequest) -> ExecuteResult:
        """Run one capability to completion. Long-running is normal; callers
        control patience via req.timeout_s. Failures return status='failed'
        with error text — raising is reserved for transport problems."""
        ...

    async def health(self) -> HealthReport: ...

    async def state(self) -> StateSnapshot: ...

    async def context(self) -> ContextDescriptor: ...

    async def knowledge(self) -> KnowledgeDescriptor: ...

    async def recent_events(self, since_id: str = "") -> list[SemanticEvent]:
        """Events this engine has emitted, oldest→newest, optionally after a
        given event_id. A small ring buffer is sufficient — durable history
        belongs to the unified event log and DataHub, not to each engine."""
        ...

    async def ingest_event(self, event: SemanticEvent) -> None:
        """Receive a fact from outside. Engines may react or ignore — the
        event never carries instructions, so autonomy is preserved."""
        ...

    async def aclose(self) -> None: ...
