"""The unified system — one product, one contract, four engines underneath.

This module assembles the composition and serves it. The served surface IS
the Universal Engine Contract (identical routes to any single engine), plus
a small product layer:

    GET  /                 the unified interface (Ask / Create)
    POST /objectives       start a composed objective (durable when Temporal
                           is up), returns immediately with an objective_id
    GET  /objectives       list objectives assembled from the event log
    GET  /objectives/{id}  one objective: stages, events, provenance, URNs
    POST /objectives/{id}/approve|reject   the human gate (Temporal signals)

Everything under the product layer is convenience. The contract routes are
the load-bearing surface: a higher-order system consumes THOSE, and cannot
tell this is a composite rather than a leaf.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from .composite import CompositeEngine
from .config import load_config
from .contract import ArtifactRef, ExecuteRequest, ExecutionRef
from .contract.http import build_engine_app
from .events.bus import EventBus
from .federation.datahub import FederationBridge
from .orchestration.launcher import try_connect
from .orchestration.stages import new_objective_id
from .remote import RemoteEngine

UI_PATH = Path(__file__).resolve().parent / "ui" / "index.html"


class ObjectiveRequest(BaseModel):
    capability: str = "compose.learning_platform"
    inputs: dict = {}


class RunArtifactRequest(BaseModel):
    """Open an artifact for real. `path` is the artifact's own recorded path;
    the engine that owns it still decides whether that path is servable."""
    path: str
    kind: str
    description: str = ""
    objective_id: str = ""


class StopArtifactRequest(BaseModel):
    container_id: str


class SignalRequest(BaseModel):
    note: str = ""


def build_unified_app() -> FastAPI:
    cfg = load_config()
    members = {name: RemoteEngine(m.url) for name, m in cfg.engines.items()}
    bus = EventBus(cfg.events_log_path)
    federation = FederationBridge(cfg.datahub_gms, cfg.unified_platform,
                                  cfg.datahub_env)
    composite = CompositeEngine(
        name=cfg.unified_name, members=members, bus=bus,
        federation=federation, datahub_platform=cfg.unified_platform,
        description=(
            "Unified intelligence: research, software engineering, "
            "education, and web generation composed into one engine that "
            "exposes the same contract it consumes."))

    async def _startup(app: FastAPI) -> None:
        await federation.probe()
        launcher = await try_connect(cfg)
        app.state.launcher = launcher
        composite.workflow_launcher = launcher
        mode = "temporal (durable)" if launcher else "inline (degraded)"
        print(f"[one-engine] orchestrator: {mode} | "
              f"datahub federation: {federation.status}")

    app = build_engine_app(composite, title="one-engine · unified",
                           on_startup=_startup)
    app.state.composite = composite
    app.state.cfg = cfg
    app.state.bus = bus
    app.state.launcher = None
    # objective_id → asyncio.Task, so a submitted objective keeps running
    # after the HTTP response returns.
    app.state.running: dict[str, asyncio.Task] = {}
    # Copies handed out and still alive, so they can be thrown away.
    app.state.dispensed: dict = {}

    # ------------------------------------------------------------------ #
    # product layer
    # ------------------------------------------------------------------ #
    @app.get("/", response_class=HTMLResponse)
    async def home():
        return UI_PATH.read_text()

    @app.post("/objectives")
    async def start_objective(req: ObjectiveRequest):
        # Validate against what THIS composite declares, not a module-level
        # registry — the same rule that keeps recursion sound.
        if req.capability not in composite.pipelines:
            raise HTTPException(
                400, f"unknown composed capability {req.capability!r}; "
                     f"available: {sorted(composite.pipelines)}")
        if not str(req.inputs.get("topic", "")).strip():
            raise HTTPException(400, "inputs.topic is required")
        objective_id = new_objective_id()
        exec_req = ExecuteRequest(
            capability=req.capability, inputs=req.inputs,
            ref=ExecutionRef(objective_id=objective_id))
        # Fire and track: composed objectives run for many minutes, so the
        # caller gets an id immediately and follows the event stream.
        task = asyncio.create_task(composite.execute(exec_req))
        app.state.running[objective_id] = task
        # Retrieve any exception as soon as the task settles, so a failed
        # objective is reported through /objectives/{id} rather than surfacing
        # as an "exception was never retrieved" warning at garbage collection.
        task.add_done_callback(
            lambda t: t.cancelled() or t.exception())
        return {"objective_id": objective_id,
                "capability": req.capability,
                "orchestrator": ("temporal" if app.state.launcher
                                 else "inline"),
                "follow": f"/objectives/{objective_id}"}

    @app.get("/objectives")
    async def list_objectives():
        ctx = await composite.context()
        return {"objectives": ctx.recent, "stats": ctx.stats}

    @app.get("/objectives/{objective_id}")
    async def get_objective(objective_id: str):
        events = [e for e in bus.recent(limit=20000)
                  if e.objective_id == objective_id]
        if not events:
            raise HTTPException(404, f"no objective {objective_id}")
        started = next((e for e in events if e.kind == "ObjectiveStarted"),
                       None)
        done = next((e for e in events if e.kind == "ObjectiveCompleted"),
                    None)
        stages = [e for e in events if e.kind == "StageCompleted"]
        progress = None
        task = app.state.running.get(objective_id)
        if app.state.launcher and not done:
            try:
                progress = await app.state.launcher.progress(objective_id)
            except Exception:
                progress = None      # workflow may not have started yet
        result = None
        if task is not None and task.done() and not task.cancelled():
            exc = task.exception()
            result = (task.result().model_dump() if exc is None
                      else {"status": "failed", "error": str(exc)})
        return {
            "objective_id": objective_id,
            "status": ("completed" if done else "running"),
            "subject": started.subject if started else "",
            "plan": (started.payload.get("stages") if started else []),
            "orchestrator": (started.payload.get("orchestrator")
                             if started else ""),
            "stages_completed": [e.payload for e in stages],
            # Every engine verdict this objective accumulated, rebuilt from
            # the log so a run inspected after a restart shows what it
            # checked rather than an empty panel.
            "verdicts": [v for e in stages
                         for v in (e.payload.get("verdicts") or [])],
            "workflow_progress": progress,
            "result": result,
            "events": [e.model_dump() for e in events],
        }

    # --- the vending path: what a run produced, and its contents ------------
    # A run's outputs live in each engine's own storage, so "where is it" was
    # answerable only by knowing four private layouts. These routes answer it
    # from the run's own record, and say whether each path was recorded by the
    # run or derived from an id it recorded.

    def _artifacts_for(objective_id: str) -> list:
        from .artifacts import engine_roots, resolve
        from .export import export_runs
        data = export_runs(cfg.events_log_path)
        obj = next((o for o in data["objectives"]
                    if o["objective_id"] == objective_id), None)
        if obj is None:
            raise HTTPException(404, f"no objective {objective_id}")
        return resolve(obj["stages"], engine_roots(), obj.get("facts"))

    @app.get("/objectives/{objective_id}/artifacts")
    async def list_artifacts(objective_id: str):
        arts = _artifacts_for(objective_id)
        return {"objective_id": objective_id,
                "artifacts": [a.as_dict() | {"index": i}
                              for i, a in enumerate(arts)]}

    @app.get("/objectives/{objective_id}/artifacts/{index}/tree")
    async def artifact_tree(objective_id: str, index: int):
        """The files inside one artifact. A single-file artifact lists itself."""
        arts = _artifacts_for(objective_id)
        if not 0 <= index < len(arts):
            raise HTTPException(404, "no such artifact")
        art = arts[index]
        root = Path(art.path)
        if not root.exists():
            raise HTTPException(404, f"artifact path is gone: {art.path}")
        if root.is_file():
            return {"kind": art.kind, "root": art.path, "origin": art.origin,
                    "files": [{"path": root.name, "size": root.stat().st_size}]}
        files = sorted(
            ({"path": str(f.relative_to(root)), "size": f.stat().st_size}
             for f in root.rglob("*") if f.is_file()),
            key=lambda d: d["path"])
        return {"kind": art.kind, "root": art.path, "origin": art.origin,
                "files": files}

    @app.get("/objectives/{objective_id}/artifacts/{index}/file")
    async def artifact_file(objective_id: str, index: int, path: str = ""):
        """One file's text.

        `path` is client-supplied, so it is resolved and then checked to be
        inside the artifact root. Serving files by a caller-provided path
        without that check is how a read surface becomes an arbitrary-file
        read; the containment test is the whole security of this route.
        """
        arts = _artifacts_for(objective_id)
        if not 0 <= index < len(arts):
            raise HTTPException(404, "no such artifact")
        root = Path(arts[index].path)
        target = root if root.is_file() else (root / path)
        try:
            resolved = target.resolve(strict=True)
            base = (root.parent if root.is_file() else root).resolve(strict=True)
            resolved.relative_to(base)
        except (OSError, ValueError):
            raise HTTPException(404, "no such file inside this artifact") from None
        if not resolved.is_file():
            raise HTTPException(404, "not a file")
        if resolved.stat().st_size > 2_000_000:
            raise HTTPException(413, "file too large to serve inline")
        return {"path": path or resolved.name,
                "size": resolved.stat().st_size,
                "text": resolved.read_text(encoding="utf-8", errors="replace")}

    @app.post("/objectives/{objective_id}/approve")
    async def approve(objective_id: str, req: SignalRequest):
        if not app.state.launcher:
            raise HTTPException(
                409, "human approval gates require the Temporal orchestrator; "
                     "this system is running inline")
        await app.state.launcher.signal(objective_id, "approve", req.note)
        return {"objective_id": objective_id, "signal": "approve"}

    @app.post("/objectives/{objective_id}/reject")
    async def reject(objective_id: str, req: SignalRequest):
        if not app.state.launcher:
            raise HTTPException(
                409, "human approval gates require the Temporal orchestrator; "
                     "this system is running inline")
        await app.state.launcher.signal(objective_id, "reject", req.note)
        return {"objective_id": objective_id, "signal": "reject"}

    # --- opening a product, not its source ---------------------------------
    # Reading generated code tells you what was written. Running it tells you
    # whether it works, which is the question a reader actually has. The
    # machinery already existed for packaging gated artifacts; these routes
    # are what let a person reach it.

    @app.post("/artifacts/run")
    async def run_artifact(req: RunArtifactRequest):
        """Build a disposable container for one artifact and hand back its URL."""
        from .vending.docker import VendingError
        from .vending.machine import package, vend

        art = ArtifactRef(kind=req.kind, path=req.path,
                          description=req.description)
        try:
            # Deliberately blocking: a build takes a while and the caller is
            # a person waiting to see the thing, not a pipeline.
            item = await asyncio.to_thread(package, art, req.objective_id or "adhoc")
            copy = await asyncio.to_thread(vend, item)
        except VendingError as e:
            # A refusal is an answer, not a fault — an unpackageable kind and
            # a broken daemon read very differently to whoever asked.
            raise HTTPException(422, str(e)) from None
        app.state.dispensed[copy.container_id] = copy
        return {"url": copy.url, "container_id": copy.container_id,
                "image": item.image, "kind": item.kind,
                "container_port": item.container_port}

    @app.post("/artifacts/stop")
    async def stop_artifact(req: StopArtifactRequest):
        """Throw the copy away. Disposable means someone has to dispose."""
        from .vending.docker import stop
        await asyncio.to_thread(stop, req.container_id)
        app.state.dispensed.pop(req.container_id, None)
        return {"stopped": req.container_id}

    @app.get("/artifacts/running")
    async def running_artifacts():
        return {"running": [{"container_id": c.container_id, "url": c.url}
                            for c in app.state.dispensed.values()]}

    @app.get("/composition")
    async def composition():
        """The recursion, rendered: the full composition tree plus what each
        level contributes. This is what makes 'a system of systems' legible
        rather than asserted."""
        manifest = await composite.describe()
        return {
            "contract_version": manifest.contract_version,
            "identity": manifest.identity.model_dump(),
            "capabilities": [c.model_dump() for c in manifest.capabilities],
            "composed_pipelines": {
                name: [{"seq": s.seq, "engine": s.engine,
                        "capability": s.capability}
                       for s in pipeline.stages]
                for name, pipeline in composite.pipelines.items()},
        }

    return app


app = build_unified_app()
