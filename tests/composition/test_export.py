"""Exporting real runs for a read-only surface.

The hosted face has none of one-engine's machinery, so it reads an export
rather than a live system. That makes this module the last place a run's record
can be quietly improved on its way to a viewer — so the tests here are almost
entirely about refusing to do that.
"""

from __future__ import annotations

import json

from entropy_os.composition.export import export_runs, write_export


def _log(tmp_path, events):
    p = tmp_path / "events.jsonl"
    p.write_text("\n".join(json.dumps(e) for e in events) + "\n")
    return p


def _started(oid, subject="topic", capability="compose.learning_platform"):
    return {"event_id": "e1", "ts": "2026-08-08T00:00:00+00:00",
            "kind": "ObjectiveStarted", "engine": "one-engine",
            "subject": subject, "objective_id": oid,
            "payload": {"capability": capability, "orchestrator": "temporal",
                        "inputs": {}, "stages": []}}


def _stage(oid, seq, engine, status="completed"):
    return {"event_id": f"s{seq}", "ts": "2026-08-08T00:01:00+00:00",
            "kind": "StageCompleted", "engine": "one-engine",
            "subject": f"urn:stage.{seq}", "objective_id": oid,
            "payload": {"seq": seq, "engine": engine, "status": status,
                        "capability": f"{engine}.do"}}


def _completed(oid, status="completed", stages=1):
    return {"event_id": "c1", "ts": "2026-08-08T00:02:00+00:00",
            "kind": "ObjectiveCompleted", "engine": "one-engine",
            "subject": f"urn:objective.{oid}", "objective_id": oid,
            "payload": {"capability": "compose.learning_platform",
                        "status": status, "stages_completed": stages}}


def _gates(oid, seq, engine, decision="proceed"):
    return {"event_id": "g1", "ts": "2026-08-08T00:01:30+00:00",
            "kind": "GatesEvaluated", "engine": "one-engine",
            "subject": f"stage.{seq}.{engine}", "objective_id": oid,
            "payload": {"stage_seq": seq, "engine": engine,
                        "decision": decision, "summary": "evidence_floor=pass",
                        "verdicts": [{"gate": "evidence_floor", "passed": True,
                                      "determinism": "hard",
                                      "evidence": "221 entities"}]}}


# --------------------------------------------------------------------------- #
# the central rule: recorded, never assumed
# --------------------------------------------------------------------------- #

def test_a_stage_without_recorded_gates_is_not_reported_as_passing(tmp_path):
    """Gate recording was added partway through this system's life, so the
    earliest runs have no verdicts. Showing green checks for verdicts nobody
    wrote down would be exactly the failure this system exists to prevent."""
    log = _log(tmp_path, [_started("obj-1"), _stage("obj-1", 1, "research"),
                          _completed("obj-1")])
    stage = export_runs(log)["objectives"][0]["stages"][0]
    assert stage["gates_recorded"] is False
    assert stage["gates"] is None


def test_unrecorded_gates_are_counted_so_a_viewer_can_say_so(tmp_path):
    """An empty gate list must not read as a clean one. The totals name the
    gap explicitly so the surface can label it."""
    log = _log(tmp_path, [
        _started("obj-1"),
        _stage("obj-1", 1, "research"), _gates("obj-1", 1, "research"),
        _stage("obj-1", 2, "software"),          # no gates recorded
        _completed("obj-1", stages=2)])
    totals = export_runs(log)["totals"]
    assert totals["stages_with_recorded_gates"] == 1
    assert totals["stages_without_recorded_gates"] == 1


def test_recorded_verdicts_survive_with_their_evidence(tmp_path):
    """A verdict's value is its evidence, not its boolean — the scaffold's
    whole point. Exporting the boolean alone would strip the reason."""
    log = _log(tmp_path, [_started("obj-1"), _stage("obj-1", 1, "research"),
                          _gates("obj-1", 1, "research"), _completed("obj-1")])
    gates = export_runs(log)["objectives"][0]["stages"][0]["gates"]
    assert gates["decision"] == "proceed"
    assert gates["verdicts"][0]["evidence"] == "221 entities"


def test_a_blocked_decision_is_exported_as_blocked(tmp_path):
    log = _log(tmp_path, [_started("obj-1"), _stage("obj-1", 1, "research"),
                          _gates("obj-1", 1, "research", decision="block"),
                          _completed("obj-1", status="failed")])
    obj = export_runs(log)["objectives"][0]
    assert obj["stages"][0]["gates"]["decision"] == "block"
    assert obj["status"] == "failed"


# --------------------------------------------------------------------------- #
# failures stay visible
# --------------------------------------------------------------------------- #

def test_failed_objectives_are_exported_not_filtered(tmp_path):
    """A surface that only shows successful runs is a brochure."""
    log = _log(tmp_path, [
        _started("obj-ok"), _stage("obj-ok", 1, "research"), _completed("obj-ok"),
        _started("obj-bad"), _stage("obj-bad", 1, "research", status="failed"),
        _completed("obj-bad", status="failed")])
    data = export_runs(log)
    assert data["totals"] == {**data["totals"], "completed": 1, "failed": 1}
    assert {o["objective_id"] for o in data["objectives"]} == {"obj-ok", "obj-bad"}


def test_an_engines_own_bad_news_is_carried_through(tmp_path):
    """The flagship run reported verification_passed: false. That fact is the
    system working, so the export must not drop it."""
    log = _log(tmp_path, [
        _started("obj-1"), _stage("obj-1", 3, "software"),
        {"event_id": "f1", "ts": "2026-08-08T00:01:10+00:00",
         "kind": "SoftwareBuilt", "engine": "one-engine", "subject": "urn:x",
         "objective_id": "obj-1",
         "payload": {"product_name": "GPUcademy", "verification_passed": False}},
        _completed("obj-1")])
    facts = export_runs(log)["objectives"][0]["facts"]
    built = next(f for f in facts if f["kind"] == "SoftwareBuilt")
    assert built["payload"]["verification_passed"] is False
    assert built["engine"] == "software"


def test_an_unfinished_run_is_running_not_completed(tmp_path):
    """A run that died mid-stage must not read as a success that merely forgot
    to say so."""
    log = _log(tmp_path, [_started("obj-1"), _stage("obj-1", 1, "research")])
    assert export_runs(log)["objectives"][0]["status"] == "running"


# --------------------------------------------------------------------------- #
# mechanics
# --------------------------------------------------------------------------- #

def test_stages_are_ordered_by_sequence_not_by_arrival(tmp_path):
    log = _log(tmp_path, [_started("obj-1"), _stage("obj-1", 3, "software"),
                          _stage("obj-1", 1, "research"),
                          _stage("obj-1", 2, "university"), _completed("obj-1")])
    seqs = [s["seq"] for s in export_runs(log)["objectives"][0]["stages"]]
    assert seqs == [1, 2, 3]


def test_narration_is_counted_in_full_but_carried_as_a_tail(tmp_path):
    """The value is showing the run really talked, not replaying every line."""
    events = [_started("obj-1")]
    events += [{"event_id": f"n{i}", "ts": "2026-08-08T00:00:30+00:00",
                "kind": "ResearchPhaseAdvanced", "engine": "one-engine",
                "subject": "t", "objective_id": "obj-1",
                "payload": {"line": f"phase {i}"}} for i in range(120)]
    events.append(_completed("obj-1"))
    obj = export_runs(_log(tmp_path, events))["objectives"][0]
    assert obj["narration_total"] == 120
    assert len(obj["narration_tail"]) == 40
    assert obj["narration_tail"][-1]["line"] == "phase 119"


def test_a_torn_final_line_does_not_lose_committed_records(tmp_path):
    """An append-only log read while being written can end mid-line. Skipping
    that costs nothing that was actually committed."""
    p = tmp_path / "events.jsonl"
    p.write_text(json.dumps(_started("obj-1")) + "\n"
                 + json.dumps(_completed("obj-1")) + "\n"
                 + '{"kind": "Objectiv')
    data = export_runs(p)
    assert len(data["objectives"]) == 1
    assert data["objectives"][0]["status"] == "completed"


def test_a_missing_log_exports_empty_rather_than_raising(tmp_path):
    """A fresh deployment has no runs yet; that is a state, not an error."""
    data = export_runs(tmp_path / "nope.jsonl")
    assert data["objectives"] == []
    assert data["totals"]["objectives"] == 0


def test_runs_appear_in_the_order_they_happened(tmp_path):
    log = _log(tmp_path, [_started("obj-a"), _completed("obj-a"),
                          _started("obj-b"), _completed("obj-b")])
    ids = [o["objective_id"] for o in export_runs(log)["objectives"]]
    assert ids == ["obj-a", "obj-b"]


def test_write_export_produces_readable_json(tmp_path):
    log = _log(tmp_path, [_started("obj-1"), _completed("obj-1")])
    out = tmp_path / "nested" / "runs.json"
    write_export(log, out)
    assert json.loads(out.read_text())["totals"]["objectives"] == 1
