"""HTTP surface of the Universal Engine Contract.

One factory serves every level of the composition tree: pass a leaf adapter
and you get that engine's contract server; pass the CompositeEngine and you
get the unified system's server. Identical routes, identical shapes — a
higher-order system pointed at either cannot tell which one it is talking to.

Routes (the contract, verbatim):

    GET  /identity        who are you (incl. recursive composition tree)
    GET  /capabilities    full manifest: what can you do
    GET  /context         what situation are you operating in
    GET  /knowledge       what do you know (pointers, not dumps)
    GET  /state           what are you doing
    GET  /health          are you well
    GET  /events          what happened (recent semantic events)
    POST /execute         do this capability
    POST /events          a fact from outside (never an instruction)
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from .protocol import ComposableEngine
from .schema import CONTRACT_VERSION, ExecuteRequest, SemanticEvent

Startup = Callable[[FastAPI], Awaitable[None]]


def build_engine_app(engine: ComposableEngine, title: str = "engine",
                     on_startup: Startup | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if on_startup is not None:
            await on_startup(app)
        yield
        await engine.aclose()

    app = FastAPI(title=title, version=CONTRACT_VERSION, docs_url="/docs",
                  lifespan=lifespan)
    # Handed to startup hooks and the unified app for mounting extras.
    app.state.engine = engine

    @app.get("/identity")
    async def identity():
        manifest = await engine.describe()
        return manifest.identity

    @app.get("/capabilities")
    async def capabilities():
        return await engine.describe()

    @app.get("/context")
    async def context():
        return await engine.context()

    @app.get("/knowledge")
    async def knowledge():
        return await engine.knowledge()

    @app.get("/state")
    async def state():
        return await engine.state()

    @app.get("/health")
    async def health():
        # A degraded engine still answers 200 — "degraded" is information,
        # not unavailability. Only transport failure should read as down.
        return await engine.health()

    @app.get("/events")
    async def events(since_id: str = ""):
        return await engine.recent_events(since_id)

    @app.post("/execute")
    async def execute(req: ExecuteRequest):
        # Contract rule: capability failures are results, not HTTP errors.
        # 500s are reserved for genuine transport/implementation faults, so
        # a composite can always distinguish "it ran and failed" from
        # "I could not reach it".
        return await engine.execute(req)

    @app.get("/artifacts/file")
    async def artifact_file(path: str, rel: str = ""):
        """One file from an artifact this engine produced.

        An ExecuteResult hands back artifact PATHS, which are useless to any
        caller that does not share the disk — and dangerous to serve naively,
        since `path` arrives from the caller. Both problems have the same
        answer: the engine that made the artifact is the one that serves it,
        and it serves nothing outside its own storage root.

        The containment check is the whole security of this route. Resolve
        first (following symlinks and `..`), then require the result to sit
        under the root; doing it in the other order checks a string rather
        than a location.
        """
        root = getattr(engine, "artifact_root", lambda: None)()
        if root is None:
            raise HTTPException(404, "this engine does not serve artifact files")
        target = Path(path)
        if rel:
            target = target / rel
        try:
            resolved = target.resolve(strict=True)
            base = Path(root).resolve(strict=True)
            resolved.relative_to(base)
        except (OSError, ValueError):
            raise HTTPException(404, "no such file inside this engine's artifacts") from None
        if not resolved.is_file():
            raise HTTPException(404, "not a file")
        if resolved.stat().st_size > 2_000_000:
            raise HTTPException(413, "file too large to serve inline")
        return {"path": str(resolved),
                "size": resolved.stat().st_size,
                "text": resolved.read_text(encoding="utf-8", errors="replace")}

    @app.post("/events", status_code=204)
    async def ingest(event: SemanticEvent):
        await engine.ingest_event(event)
        return JSONResponse(status_code=204, content=None)

    return app
