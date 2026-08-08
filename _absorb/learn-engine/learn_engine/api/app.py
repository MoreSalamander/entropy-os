"""FastAPI surface.

  POST /study {"goal": …}                start a session (roadmap + research)
  GET  /study/{id}                       session state + mastery snapshot
  POST /study/{id}/next                  adaptive next activity (lesson/exercises)
  POST /study/{id}/answer {"answers": {ex_id: text}}   grade + update mastery
  GET  /knowledge/stats                  education KG shape
  GET  /knowledge/gaps?concept=&mastered=a,b   missing-prerequisite query
  GET  /knowledge/bridges?goal=&mastered=a,b   cross-disciplinary paths

Run:  .venv/bin/uvicorn learn_engine.api.app:app --port 8020
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from ..engine import LearnEngine

app = FastAPI(title="learn-engine", version="0.1.0")
_sessions: dict[str, dict[str, Any]] = {}


class StudyRequest(BaseModel):
    goal: str
    learner_name: str = "learner"


class AnswerRequest(BaseModel):
    answers: dict[str, str]


def _find(session_id: str) -> dict:
    state = _sessions.get(session_id)
    if state is None:
        raise HTTPException(404, f"unknown session {session_id}")
    return state


@app.post("/study")
async def start_study(req: StudyRequest) -> dict:
    if not req.goal.strip():
        raise HTTPException(400, "goal is required")
    engine = LearnEngine()
    state: dict[str, Any] = {"engine": engine, "log": [], "phase": "starting",
                             "activity": None, "error": None, "id": None}

    async def run() -> None:
        try:
            roadmap = await engine.start(req.goal, req.learner_name,
                                         log=state["log"].append)
            state["id"] = engine.session_id
            _sessions[engine.session_id] = state
            state["roadmap"] = json.loads(roadmap.model_dump_json())
            state["phase"] = "ready"
        except Exception as e:  # noqa: BLE001 — API boundary
            state["phase"] = "failed"
            state["error"] = f"{type(e).__name__}: {e}"

    provisional = f"pending_{len(_sessions)}"
    state["id"] = provisional
    _sessions[provisional] = state
    state["task"] = asyncio.create_task(run())
    return {"session_id": provisional, "note": "poll GET /study/{id}"}


@app.get("/study/{session_id}")
async def get_study(session_id: str) -> dict:
    s = _find(session_id)
    engine: LearnEngine = s["engine"]
    out = {"id": s.get("id"), "phase": s["phase"], "error": s["error"],
           "log": s["log"][-30:]}
    if engine.cg is not None:
        out["snapshot"] = engine.cg.snapshot()
    return out


@app.post("/study/{session_id}/next")
async def next_activity_ep(session_id: str) -> dict:
    s = _find(session_id)
    if s["phase"] != "ready":
        raise HTTPException(409, f"session is {s['phase']}")
    engine: LearnEngine = s["engine"]
    activity = await engine.next(log=s["log"].append)
    if activity is None:
        return {"done": True, "message": "roadmap fully mastered"}
    s["activity"] = activity
    payload = json.loads(activity.model_dump_json())
    # answers/reference solutions never ship to the client
    for ex in payload.get("exercises", []):
        ex.pop("answer", None)
        ex.pop("reference_solution", None)
    if payload.get("lesson"):
        for ex in payload["lesson"].get("exercises", []):
            ex.pop("answer", None)
            ex.pop("reference_solution", None)
    return {"done": False, "activity": payload}


@app.post("/study/{session_id}/answer")
async def answer_ep(session_id: str, req: AnswerRequest) -> dict:
    s = _find(session_id)
    engine: LearnEngine = s["engine"]
    activity = s.get("activity")
    if activity is None:
        raise HTTPException(409, "no active activity — call /next first")
    graded = await engine.submit(activity, req.answers, log=s["log"].append)
    s["activity"] = None
    return {"graded": [json.loads(g.model_dump_json()) for g in graded],
            "mastery": {k: v.level.value
                        for k, v in engine.profile.mastery.items()}}


# module-level engine for KG queries independent of sessions
_kg_engine = LearnEngine()


@app.get("/knowledge/stats")
async def kg_stats() -> dict:
    return _kg_engine.kg.stats()


@app.get("/knowledge/gaps")
async def kg_gaps(concept: str, mastered: str = "") -> dict:
    known = [m.strip() for m in mastered.split(",") if m.strip()]
    return {"concept": concept, "mastered": known,
            "missing_prerequisites":
                _kg_engine.kg.missing_prerequisites(concept, known)}


@app.get("/knowledge/bridges")
async def kg_bridges(goal: str, mastered: str = "") -> dict:
    known = [m.strip() for m in mastered.split(",") if m.strip()]
    return {"goal": goal, "mastered": known,
            "paths": _kg_engine.kg.cross_disciplinary(known, goal)}
