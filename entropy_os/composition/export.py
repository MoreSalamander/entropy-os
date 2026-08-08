"""Export real completed runs as a portable record.

Entropy OS serves a read-only view of one-engine's work on its hosted face,
where none of one-engine's machinery exists — no Temporal, no DataHub, no
Ollama, no four engine processes. So the hosted surface reads an export rather
than a live system, and this module produces it.

The source is the **durable event log**, not DataHub. Two reasons: the log is
what survives a DataHub outage (the search index went down once and made every
dataset invisible while remaining perfectly durable in MySQL), and the log is
the record the run itself wrote as it happened, rather than a projection of it.

**The rule this module exists to keep: export what was recorded, never what
was probably true.** Gate verdicts were added to the recorder partway through
this system's life, so the earliest runs — including the flagship — have no
recorded verdicts. Those stages export with `gates: null` and
`gates_recorded: false`, never a synthesized pass. A viewer that showed green
checks for verdicts nobody wrote down would be exactly the failure this whole
system is built to prevent.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from .contract import now_iso

# Events that carry an engine's own domain facts — the numbers worth showing.
# Everything else is either orchestration bookkeeping or per-phase narration.
DOMAIN_FACTS = {
    "ResearchCompleted": "research",
    "KnowledgeConsolidated": "research",
    "CurriculumCreated": "university",
    "SoftwareBuilt": "software",
    "SoftwareVerificationFailed": "software",
    "SiteGenerated": "web",
}

# High-volume per-phase narration. Kept as a tail rather than in full: the
# value is showing that the run really talked, not replaying every line.
NARRATION = {"ResearchPhaseAdvanced", "SoftwareBuildProgress",
             "SiteGenerationProgress"}
NARRATION_TAIL = 40


def _load(events_path: Path) -> list[dict[str, Any]]:
    if not events_path.exists():
        return []
    events: list[dict[str, Any]] = []
    with events_path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                # A torn final line is normal for an append-only log being
                # written while it is read. Skipping it loses nothing that
                # was actually committed.
                continue
    return events


def export_runs(events_path: Path) -> dict[str, Any]:
    """Group the event log into per-objective records.

    Ordering follows the log, so a run appears in the order it actually
    happened rather than in an order chosen to flatter it.
    """
    events = _load(events_path)
    by_objective: dict[str, list[dict[str, Any]]] = defaultdict(list)
    order: list[str] = []
    for e in events:
        oid = e.get("objective_id")
        if not oid:
            continue
        if oid not in by_objective:
            order.append(oid)
        by_objective[oid].append(e)

    objectives = [_one_objective(oid, by_objective[oid]) for oid in order]
    return {
        "generated_at": now_iso(),
        "source": str(events_path),
        "objectives": objectives,
        "totals": _totals(objectives),
    }


def _one_objective(oid: str, events: list[dict[str, Any]]) -> dict[str, Any]:
    started = next((e for e in events if e["kind"] == "ObjectiveStarted"), None)
    completed = next((e for e in events
                      if e["kind"] == "ObjectiveCompleted"), None)
    start_payload = (started or {}).get("payload", {})
    end_payload = (completed or {}).get("payload", {})

    stages = _stages(events)
    facts = _facts(events)
    narration = [{"ts": e["ts"], "kind": e["kind"],
                  "line": e.get("payload", {}).get("line", "")}
                 for e in events if e["kind"] in NARRATION]

    impact = next((e["payload"] for e in events
                   if e["kind"] == "ImpactAnalyzed"), None)

    return {
        "objective_id": oid,
        "subject": (started or {}).get("subject", ""),
        "capability": start_payload.get("capability", ""),
        "orchestrator": start_payload.get("orchestrator", ""),
        "inputs": start_payload.get("inputs", {}),
        "stages_planned": start_payload.get("stages", []),
        "started_at": (started or {}).get("ts", ""),
        # An objective with no completion event is reported as running rather
        # than assumed finished: a run that died mid-stage must not read as a
        # success that simply forgot to say so.
        "status": end_payload.get("status", "running" if started else "unknown"),
        "completed_at": (completed or {}).get("ts", ""),
        "stages_completed": end_payload.get("stages_completed", 0),
        "datahub": end_payload.get("datahub", ""),
        "objective_urn": (completed or {}).get("subject", ""),
        "concept_urn": end_payload.get("concept_urn", ""),
        "impact": impact,
        "stages": stages,
        "facts": facts,
        "narration_total": len(narration),
        "narration_tail": narration[-NARRATION_TAIL:],
    }


def _stages(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One record per stage, with its gate verdicts when they were recorded.

    Gates are matched to stages by sequence number. A stage with no matching
    `GatesEvaluated` is marked unrecorded rather than assumed to have passed —
    see the module docstring.
    """
    gates_by_seq: dict[int, dict[str, Any]] = {}
    for e in events:
        if e["kind"] == "GatesEvaluated":
            p = e["payload"]
            gates_by_seq[int(p.get("stage_seq", -1))] = p

    stages: list[dict[str, Any]] = []
    for e in events:
        if e["kind"] != "StageCompleted":
            continue
        p = e["payload"]
        seq = int(p.get("seq", -1))
        gate = gates_by_seq.get(seq)
        stages.append({
            "seq": seq,
            "engine": p.get("engine", ""),
            "capability": p.get("capability", ""),
            "status": p.get("status", ""),
            "urn": e.get("subject", ""),
            "ts": e.get("ts", ""),
            "produced": p.get("produced", {}),
            # Recorded from the run itself when present. Absent on the earliest
            # runs, which is why entropy_os.composition.artifacts exists to resolve those by
            # convention — and to say that is what it did.
            "artifacts": p.get("artifacts", []),
            "gates_recorded": gate is not None,
            "gates": None if gate is None else {
                "decision": gate.get("decision", ""),
                "summary": gate.get("summary", ""),
                "verdicts": gate.get("verdicts", []),
            },
        })
    return sorted(stages, key=lambda s: s["seq"])


def _facts(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The engines' own domain numbers, in the order they were reported."""
    return [{"engine": DOMAIN_FACTS[e["kind"]], "kind": e["kind"],
             "subject": e.get("subject", ""), "payload": e.get("payload", {})}
            for e in events if e["kind"] in DOMAIN_FACTS]


def _totals(objectives: list[dict[str, Any]]) -> dict[str, Any]:
    """Headline counts. Failures are counted and shown, not filtered out."""
    stages = [s for o in objectives for s in o["stages"]]
    gated = [s for s in stages if s["gates_recorded"]]
    engines = {s["engine"] for s in stages if s["engine"]}
    return {
        "objectives": len(objectives),
        "completed": sum(1 for o in objectives if o["status"] == "completed"),
        "failed": sum(1 for o in objectives if o["status"] == "failed"),
        "stages": len(stages),
        "engines": sorted(engines),
        # Stated explicitly so a viewer can say "verdicts were not recorded for
        # these" instead of quietly showing an empty gate list as if it were a
        # clean one.
        "stages_with_recorded_gates": len(gated),
        "stages_without_recorded_gates": len(stages) - len(gated),
    }


def write_export(events_path: Path, out_path: Path) -> dict[str, Any]:
    data = export_runs(events_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return data
