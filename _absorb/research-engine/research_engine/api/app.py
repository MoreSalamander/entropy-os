"""FastAPI surface.

  POST /research {"topic": ...}      start a session (runs in background)
  GET  /research/{id}                phase + live counters + report when done
  GET  /research/{id}/report.md      rendered markdown report
  GET  /research/{id}/events         SSE stream of ProgressEvents
  GET  /graph/context/{id}           the session's Context Graph snapshot
  GET  /graph/knowledge/stats        KG size and reach
  GET  /graph/knowledge/entity/{name}  node + edges by (fuzzy-normalized) name
  GET  /graph/knowledge/paths        cross-domain paths between two names
  GET  /sources/status               the honesty table

Run:  .venv/bin/uvicorn research_engine.api.app:app --port 8017
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse, StreamingResponse
from pydantic import BaseModel

from ..engine import Engine
from ..models import ProgressEvent, SessionPhase
from ..report.builder import ReportBuilder

app = FastAPI(title="research-engine", version="0.1.0")
engine = Engine()

# In-process session registry: id -> {phase, events, report, cg, task}
_sessions: dict[str, dict[str, Any]] = {}


class ResearchRequest(BaseModel):
    topic: str


@app.on_event("startup")
async def _startup() -> None:
    await engine.init()


@app.on_event("shutdown")
async def _shutdown() -> None:
    await engine.aclose()


async def _run_session(sid_holder: dict, topic: str) -> None:
    state = sid_holder

    async def progress(ev: ProgressEvent) -> None:
        state["phase"] = ev.phase.value
        state["events"].append(ev)
        state["queue"].put_nowait(ev)

    try:
        report, cg = await engine.research(topic, progress)
        state["report"] = report
        state["cg"] = cg
        state["id"] = report.session_id
        _sessions[report.session_id] = state
        state["phase"] = SessionPhase.DONE.value
    except Exception as e:  # noqa: BLE001 — API boundary: fail visibly, not silently
        state["phase"] = SessionPhase.FAILED.value
        state["error"] = f"{type(e).__name__}: {e}"
    finally:
        state["queue"].put_nowait(None)  # closes any open SSE streams


@app.post("/research")
async def start_research(req: ResearchRequest) -> dict:
    if not req.topic.strip():
        raise HTTPException(400, "topic is required")
    state: dict[str, Any] = {"topic": req.topic, "phase": SessionPhase.PLANNING.value,
                             "events": [], "report": None, "cg": None,
                             "queue": asyncio.Queue(), "error": None}
    # provisional id until the engine assigns the real session id
    provisional = f"pending_{len(_sessions)}_{abs(hash(req.topic)) % 10_000}"
    state["id"] = provisional
    _sessions[provisional] = state
    state["task"] = asyncio.create_task(_run_session(state, req.topic))
    return {"session_id": provisional,
            "note": "id becomes the final session id once planning assigns it; "
                    "poll GET /research/{id}"}


def _find(session_id: str) -> dict:
    state = _sessions.get(session_id)
    if state is None:
        raise HTTPException(404, f"unknown session {session_id}")
    return state


@app.get("/research/{session_id}")
async def get_research(session_id: str) -> dict:
    s = _find(session_id)
    out: dict[str, Any] = {"id": s.get("id"), "topic": s["topic"],
                           "phase": s["phase"], "error": s["error"],
                           "events_seen": len(s["events"])}
    if s["report"] is not None:
        out["report"] = json.loads(s["report"].model_dump_json())
    return out


@app.get("/research/{session_id}/report.md", response_class=PlainTextResponse)
async def get_report_md(session_id: str) -> str:
    s = _find(session_id)
    if s["report"] is None:
        raise HTTPException(409, f"session is {s['phase']}; report not ready")
    return ReportBuilder.to_markdown(s["report"])


@app.get("/research/{session_id}/events")
async def get_events(session_id: str) -> StreamingResponse:
    s = _find(session_id)

    async def stream():
        for ev in s["events"]:  # replay history, then follow live
            yield f"data: {ev.model_dump_json()}\n\n"
        while s["phase"] not in (SessionPhase.DONE.value, SessionPhase.FAILED.value):
            ev = await s["queue"].get()
            if ev is None:
                break
            yield f"data: {ev.model_dump_json()}\n\n"
        yield f"data: {json.dumps({'phase': s['phase'], 'final': True})}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


@app.get("/graph/context/{session_id}")
async def get_context_graph(session_id: str) -> dict:
    s = _find(session_id)
    if s["cg"] is None:
        raise HTTPException(409, "context graph not built yet")
    return s["cg"].snapshot()


@app.get("/graph/knowledge/stats")
async def kg_stats() -> dict:
    return engine.kg.stats()


@app.get("/graph/knowledge/entity/{name}")
async def kg_entity(name: str) -> dict:
    node_id = engine.kg.find_by_name(name)
    if node_id is None:
        raise HTTPException(404, f"no KG entity named '{name}'")
    return {"id": node_id,
            "node": engine.kg.store.get_node(node_id),
            "edges": [{"src": s_, "dst": d, "key": k, "props": p}
                      for s_, d, k, p in engine.kg.store.edges_of(node_id)]}


@app.get("/graph/knowledge/paths")
async def kg_paths(a: str, b: str, cutoff: int = 4) -> dict:
    return {"a": a, "b": b,
            "paths": engine.kg.paths_between_names(a, b, cutoff)}


@app.get("/sources/status")
async def sources_status() -> list[dict]:
    return engine.registry.status_table()
