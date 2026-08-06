"""Collector HTTP endpoints — the front door's view over the engine-room collector.

Split out of veritas tests/test_collector.py when the web surface moved here;
the collector logic tests stayed with the collector. Helpers are copied, not
imported — test files in both repos stay self-contained by convention.
"""

import json
import sqlite3
from pathlib import Path

import pytest

from collector.sources import SourceConfig

def _hunter_engine_source(tmp_path: Path, name: str = "crypto_hunter", **kw: object) -> SourceConfig:
    repo = tmp_path / name
    (repo / "data").mkdir(parents=True, exist_ok=True)
    kwargs = {"name": name, "title": name, "repo": str(repo), "kind": "hunter_engine", "color": "fff"}
    kwargs.update(kw)
    return SourceConfig(**kwargs)  # type: ignore[arg-type]


def _write_hunter_engine_db(repo: Path, rows: list[tuple[str, dict[str, object]]]) -> None:
    db_path = repo / "data" / "datahub.sqlite3"
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE opportunities (id TEXT PRIMARY KEY, name TEXT, type TEXT,"
        " trust_status TEXT, lifecycle TEXT, spec_json TEXT)"
    )
    for opp_id, spec in rows:
        conn.execute(
            "INSERT INTO opportunities (id, name, type, trust_status, lifecycle, spec_json)"
            " VALUES (?, ?, ?, 'verified', 'gated', ?)",
            (opp_id, spec.get("name", opp_id), spec.get("type", "generic"), json.dumps(spec)),
        )
    conn.commit()
    conn.close()


def _verified_spec(**overrides: object) -> dict[str, object]:
    spec: dict[str, object] = {
        "name": "Some Opportunity",
        "type": "airdrop",
        "cost_usd_est": 5.0,
        "verification": [{"check": "domain_age", "passed": True, "data": {}}],
        "outcome": {"payout_usd_est": None},
    }
    spec.update(overrides)
    return spec


# --- readers -----------------------------------------------------------------------------------



@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from fastapi.testclient import TestClient

    import entropy_os.app as app_mod

    monkeypatch.delenv("VERITAS_ACCOUNTS", raising=False)
    cfg = _hunter_engine_source(tmp_path, name="crypto_hunter", default_trust="held")
    _write_hunter_engine_db(Path(cfg.repo), [("opp1", _verified_spec(name="Test Opp"))])
    fixed_sources = {"crypto_hunter": cfg}
    monkeypatch.setattr(app_mod, "load_sources", lambda _path: fixed_sources)

    app = app_mod.create_app(data_dir=tmp_path / "hub_data")
    return TestClient(app)


def test_collector_pending_endpoint_returns_held_records(client) -> None:
    client.post("/api/collector/collect")
    resp = client.get("/api/collector/pending")
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["source"] == "crypto_hunter"


def test_collector_approve_endpoint_transitions_state(client) -> None:
    client.post("/api/collector/collect")
    pending = client.get("/api/collector/pending").json()
    rid = pending[0]["id"]
    resp = client.post(f"/api/collector/records/{rid}/approve")
    assert resp.status_code == 200
    assert resp.json()["state"] == "admitted"
    assert client.get("/api/collector/pending").json() == []


def test_collector_approve_unknown_id_is_404(client) -> None:
    resp = client.post("/api/collector/records/nonexistent/approve")
    assert resp.status_code == 404


def test_collector_decline_endpoint_transitions_state(client) -> None:
    client.post("/api/collector/collect")
    pending = client.get("/api/collector/pending").json()
    rid = pending[0]["id"]
    resp = client.post(f"/api/collector/records/{rid}/decline")
    assert resp.status_code == 200
    assert resp.json()["state"] == "declined"
