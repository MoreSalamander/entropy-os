"""FastAPI surface.

  POST /build {"request": …}          idea → generated+verified project (background)
  GET  /builds/{id}                   phase log + result
  GET  /projects/{dir}/impact/{component}   change-impact from the sidecar
  POST /projects/evolve {"dir": …}    evolution health check
  GET  /knowledge/patterns            cross-project pattern priors
  GET  /knowledge/stats               KG shape

Run:  .venv/bin/uvicorn entropy_os.engines.software.api.app:app --port 8019
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from ..engine import CodeEngine
from ..graphs.context_graph import SoftwareContextGraph
from ..impact import analyze_impact

app = FastAPI(title="code-engine", version="0.1.0")
engine = CodeEngine()
_builds: dict[str, dict[str, Any]] = {}


class BuildRequest(BaseModel):
    request: str


class EvolveRequest(BaseModel):
    dir: str


@app.on_event("shutdown")
async def _shutdown() -> None:
    await engine.aclose()


async def _run(state: dict, req: BuildRequest) -> None:
    def log(line: str) -> None:
        state["log"].append(str(line))

    try:
        project = await engine.build(req.request, log=log)
        state["project"] = json.loads(project.model_dump_json())
        state["id"] = project.project_id
        _builds[project.project_id] = state
        state["phase"] = "done"
    except Exception as e:  # noqa: BLE001 — API boundary: fail visibly
        state["phase"] = "failed"
        state["error"] = f"{type(e).__name__}: {e}"


@app.post("/build")
async def build(req: BuildRequest) -> dict:
    if not req.request.strip():
        raise HTTPException(400, "request is required")
    state: dict[str, Any] = {"request": req.request, "phase": "running",
                             "log": [], "project": None, "error": None}
    provisional = f"pending_{len(_builds)}"
    state["id"] = provisional
    _builds[provisional] = state
    state["task"] = asyncio.create_task(_run(state, req))
    return {"build_id": provisional}


@app.get("/builds/{build_id}")
async def get_build(build_id: str) -> dict:
    state = _builds.get(build_id)
    if state is None:
        raise HTTPException(404, f"unknown build {build_id}")
    return {"id": state.get("id"), "request": state["request"],
            "phase": state["phase"], "error": state["error"],
            "log": state["log"], "project": state["project"]}


@app.get("/projects/impact")
async def impact(dir: str, component: str) -> dict:
    root = Path(dir)
    try:
        cg = SoftwareContextGraph.load_sidecar(root)
        return json.loads(analyze_impact(cg, component).model_dump_json())
    except FileNotFoundError:
        raise HTTPException(404, f"no sidecar model under {dir}")
    except KeyError as e:
        raise HTTPException(404, str(e))


@app.post("/projects/evolve")
async def evolve_project(req: EvolveRequest) -> dict:
    from ..evolve import evolve
    root = Path(req.dir)
    if not root.exists():
        raise HTTPException(404, f"no such directory {req.dir}")
    findings = await evolve(root, engine.llm, log=lambda *_: None)
    return {"findings": [json.loads(f.model_dump_json()) for f in findings]}


@app.get("/knowledge/patterns")
async def patterns() -> list[dict]:
    return engine.kg.pattern_priors()


@app.get("/knowledge/stats")
async def kg_stats() -> dict:
    return engine.kg.stats()
