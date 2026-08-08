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
from .contract import ExecuteRequest, ExecutionRef
from .contract.http import build_engine_app
from .events.bus import EventBus
from .federation.datahub import FederationBridge
from .orchestration.launcher import try_connect
from .orchestration.stages import COMPOSED_PIPELINES, new_objective_id
from .remote import RemoteEngine

UI_PATH = Path(__file__).resolve().parent / "ui" / "index.html"


class ObjectiveRequest(BaseModel):
    capability: str = "compose.learning_platform"
    inputs: dict = {}


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

    # ------------------------------------------------------------------ #
    # product layer
    # ------------------------------------------------------------------ #
    @app.get("/", response_class=HTMLResponse)
    async def home():
        return UI_PATH.read_text()

    @app.post("/objectives")
    async def start_objective(req: ObjectiveRequest):
        if req.capability not in COMPOSED_PIPELINES:
            raise HTTPException(
                400, f"unknown composed capability {req.capability!r}; "
                     f"available: {sorted(COMPOSED_PIPELINES)}")
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
            "workflow_progress": progress,
            "result": result,
            "events": [e.model_dump() for e in events],
        }

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
