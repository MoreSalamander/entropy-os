"""RemoteEngine — the recursion mechanism.

A ComposableEngine implementation that fulfills the whole protocol by talking
to any contract server over HTTP. This one class is how EVERYTHING composes:

  * the unified CompositeEngine holds four RemoteEngines (one per adapter
    server running inside its engine's own venv);
  * a second-level system holds ONE RemoteEngine pointed at the unified
    system's URL — and cannot tell, from anything in this class, that four
    engines live behind it.

If composition ever needed a different mechanism at a different level, the
recursion claim would be false. It doesn't: same class, every level.
"""

from __future__ import annotations

import httpx

from .contract.schema import (
    ArtifactNotServed,
    ContextDescriptor,
    EngineManifest,
    ExecuteRequest,
    ExecuteResult,
    HealthReport,
    KnowledgeDescriptor,
    SemanticEvent,
    StateSnapshot,
)


class RemoteEngine:
    def __init__(self, base_url: str, connect_timeout_s: float = 5.0):
        self.base_url = base_url.rstrip("/")
        # Read timeout is per-call (execute honors the request's timeout_s);
        # connect stays short so a down engine is discovered quickly.
        self._connect_timeout = connect_timeout_s
        self._client = httpx.AsyncClient(base_url=self.base_url)

    def _timeout(self, read_s: float) -> httpx.Timeout:
        return httpx.Timeout(connect=self._connect_timeout, read=read_s,
                             write=30.0, pool=self._connect_timeout)

    async def describe(self) -> EngineManifest:
        r = await self._client.get("/capabilities", timeout=self._timeout(30))
        r.raise_for_status()
        return EngineManifest.model_validate(r.json())

    async def execute(self, req: ExecuteRequest) -> ExecuteResult:
        # Engines do real work (research runs, code generation, site builds);
        # the HTTP read window must outlive the capability, so it follows the
        # request's own declared patience plus margin for serialization.
        r = await self._client.post("/execute", json=req.model_dump(),
                                    timeout=self._timeout(req.timeout_s + 60))
        r.raise_for_status()
        return ExecuteResult.model_validate(r.json())

    async def health(self) -> HealthReport:
        r = await self._client.get("/health", timeout=self._timeout(15))
        r.raise_for_status()
        return HealthReport.model_validate(r.json())

    async def state(self) -> StateSnapshot:
        r = await self._client.get("/state", timeout=self._timeout(15))
        r.raise_for_status()
        return StateSnapshot.model_validate(r.json())

    async def context(self) -> ContextDescriptor:
        r = await self._client.get("/context", timeout=self._timeout(30))
        r.raise_for_status()
        return ContextDescriptor.model_validate(r.json())

    async def knowledge(self) -> KnowledgeDescriptor:
        r = await self._client.get("/knowledge", timeout=self._timeout(30))
        r.raise_for_status()
        return KnowledgeDescriptor.model_validate(r.json())

    async def recent_events(self, since_id: str = "") -> list[SemanticEvent]:
        r = await self._client.get("/events", params={"since_id": since_id},
                                   timeout=self._timeout(15))
        r.raise_for_status()
        return [SemanticEvent.model_validate(e) for e in r.json()]

    async def ingest_event(self, event: SemanticEvent) -> None:
        r = await self._client.post("/events", json=event.model_dump(),
                                    timeout=self._timeout(15))
        r.raise_for_status()

    async def artifact_file(self, path: str, rel: str = "") -> dict:
        """Ask the engine that owns the artifact. Containment is enforced on
        ITS side, by the only party that knows what it owns."""
        r = await self._client.get(f"{self.base_url}/artifacts/file",
                                   params={"path": path, "rel": rel},
                                   timeout=self._timeout(30.0))
        if r.status_code != 200:
            raise ArtifactNotServed(f"{self.base_url} refused: {r.status_code}")
        return dict(r.json())

    async def artifact_tree(self, path: str) -> dict:
        r = await self._client.get(f"{self.base_url}/artifacts/tree",
                                   params={"path": path},
                                   timeout=self._timeout(30.0))
        if r.status_code != 200:
            raise ArtifactNotServed(f"{self.base_url} refused: {r.status_code}")
        return dict(r.json())

    async def aclose(self) -> None:
        await self._client.aclose()
