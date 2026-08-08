"""FastAPI surface.

  POST /generate {"request": …, "build": bool}   start a project (background)
  GET  /projects/{id}                            phase log + result
  GET  /projects/{id}/review                     review report
  GET  /graph/knowledge/stats                    Design KG shape
  GET  /graph/knowledge/priors/{industry}        learned industry priors
  POST /projects/{id}/feedback {…}               human feedback → memory loop

Run:  .venv/bin/uvicorn design_engine.api.app:app --port 8018
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from ..engine import DesignEngine

app = FastAPI(title="design-engine", version="0.1.0")
engine = DesignEngine()
_projects: dict[str, dict[str, Any]] = {}


class GenerateRequest(BaseModel):
    request: str
    build: bool = False


class FeedbackRequest(BaseModel):
    feedback: dict


@app.on_event("shutdown")
async def _shutdown() -> None:
    await engine.aclose()


async def _run(state: dict, req: GenerateRequest) -> None:
    def log(line: str) -> None:
        state["log"].append(str(line))

    try:
        site = await engine.generate(req.request, build_gate=req.build, log=log)
        state["site"] = json.loads(site.model_dump_json())
        state["id"] = site.project_id
        _projects[site.project_id] = state
        state["phase"] = "done"
    except Exception as e:  # noqa: BLE001 — API boundary: fail visibly
        state["phase"] = "failed"
        state["error"] = f"{type(e).__name__}: {e}"


@app.post("/generate")
async def generate(req: GenerateRequest) -> dict:
    if not req.request.strip():
        raise HTTPException(400, "request is required")
    state: dict[str, Any] = {"request": req.request, "phase": "running",
                             "log": [], "site": None, "error": None}
    provisional = f"pending_{len(_projects)}"
    state["id"] = provisional
    _projects[provisional] = state
    state["task"] = asyncio.create_task(_run(state, req))
    return {"project_id": provisional,
            "note": "id becomes the real project id once assigned; poll GET /projects/{id}"}


def _find(project_id: str) -> dict:
    state = _projects.get(project_id)
    if state is None:
        raise HTTPException(404, f"unknown project {project_id}")
    return state


@app.get("/projects/{project_id}")
async def get_project(project_id: str) -> dict:
    s = _find(project_id)
    return {"id": s.get("id"), "request": s["request"], "phase": s["phase"],
            "error": s["error"], "log": s["log"], "site": s["site"]}


@app.get("/projects/{project_id}/review")
async def get_review(project_id: str) -> dict:
    s = _find(project_id)
    if not s["site"]:
        raise HTTPException(409, f"project is {s['phase']}")
    return s["site"]["review"]


@app.post("/projects/{project_id}/feedback")
async def post_feedback(project_id: str, req: FeedbackRequest) -> dict:
    ok = engine.kg.record_feedback(project_id, req.feedback)
    if not ok:
        raise HTTPException(404, f"no recorded outcome for {project_id}")
    return {"recorded": True}


@app.get("/graph/knowledge/stats")
async def kg_stats() -> dict:
    return engine.kg.stats()


@app.get("/graph/knowledge/priors/{industry}")
async def kg_priors(industry: str) -> dict:
    return engine.kg.priors_for(industry)
