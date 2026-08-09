"""Wedge HTTP surface — storefront + auth + streaming submit, over entropy_os.app.

Split out of veritas tests/test_wedge.py when the web surface moved here; the
wedge-core logic tests live beside it in tests/test_wedge_core.py.
"""

from __future__ import annotations

import json

from engine.model import ScriptedProvider

from entropy_os.wedge import Wedge, WedgeAuth

from .conftest import fake_execute

GOOD_SPEC = json.dumps({
    "function_name": "add", "description": "add two numbers", "signature": "def add(a, b)",
    "cases": [{"args": [1, 2], "expected": 3}, {"args": [5, 5], "expected": 10}],
})
GOOD_CODE = "def add(a, b):\n    return a + b\n"


def _provider() -> ScriptedProvider:
    return ScriptedProvider({"spec": GOOD_SPEC, "developer": GOOD_CODE})


def _wedge(tmp_path, *, sandbox=True, tokens=None) -> Wedge:
    auth = WedgeAuth(tokens or {"tok_alice": "alice"})
    return Wedge(tmp_path, _provider, auth, sandbox_check=lambda: sandbox,
                 execute=fake_execute())


# --- auth: the identity floor ----------------------------------------------------------------


def test_http_status_and_submit(tmp_path, monkeypatch):
    from engine.executor import ContainerExecutor
    from fastapi.testclient import TestClient

    from entropy_os.app import create_app

    # Fake the sandbox as live without a Docker daemon: default_executor() reports a container, so
    # sandbox_active() (used by both the status endpoint and the wedge) returns True.
    monkeypatch.setattr("engine.executor.default_executor", lambda: ContainerExecutor())
    monkeypatch.setenv("VERITAS_WEDGE_TOKENS", "tok_alice:alice")
    client = TestClient(create_app(data_dir=tmp_path, provider=_provider(), execute=fake_execute()))

    status = client.get("/api/wedge/status").json()
    assert status == {"sandbox_active": True, "auth_configured": True,
                      "accounts": False, "metered": False, "open": True}

    assert client.post("/api/wedge/submit", json={"goal": "add"}).status_code == 401  # no token
    ok = client.post("/api/wedge/submit", json={"goal": "add two numbers"},
                     headers={"Authorization": "Bearer tok_alice"})
    assert ok.status_code == 200 and ok.json()["accepted"] and ok.json()["tenant"] == "alice"


def test_wedge_page_is_served(tmp_path):
    from fastapi.testclient import TestClient

    from entropy_os.app import create_app

    client = TestClient(create_app(data_dir=tmp_path, provider=_provider(), execute=fake_execute()))
    for path in ("/wedge", "/try"):
        r = client.get(path)
        assert r.status_code == 200
        # the storefront wiring
        assert "/api/wedge/submit" in r.text and "/api/auth/login" in r.text


def test_public_mode_exposes_only_the_wedge(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from entropy_os.app import create_app

    monkeypatch.setenv("ENTROPY_PUBLIC", "1")
    client = TestClient(create_app(data_dir=tmp_path, provider=_provider(), execute=fake_execute()))

    # the wedge surface is reachable
    assert client.get("/api/wedge/status").status_code == 200
    assert client.get("/wedge").status_code == 200
    # root redirects to the storefront, not the admin dashboard
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 307 and r.headers["location"] == "/wedge"
    # the admin/unauthenticated surface is sealed off
    for blocked in ("/api/runs", "/api/dashboard", "/api/commons", "/about"):
        assert client.get(blocked).status_code == 404, blocked


def test_streaming_submit_emits_trace_then_result(tmp_path, monkeypatch):
    import time

    from engine.executor import ContainerExecutor
    from fastapi.testclient import TestClient

    from entropy_os.app import create_app

    monkeypatch.setattr("engine.executor.default_executor", lambda: ContainerExecutor())
    monkeypatch.setenv("VERITAS_WEDGE_TOKENS", "tok_alice:alice")
    client = TestClient(create_app(data_dir=tmp_path, provider=_provider(), execute=fake_execute()))
    hdr = {"Authorization": "Bearer tok_alice"}

    # anon refused
    assert client.post("/api/wedge/submit/start", json={"goal": "x"}).status_code == 401
    token = client.post("/api/wedge/submit/start", json={"goal": "add two numbers"},
                        headers=hdr).json()["token"]

    state = {}
    for _ in range(100):  # poll the live trace until the background build finishes
        state = client.get(f"/api/wedge/submit/progress/{token}").json()
        if state.get("done"):
            break
        time.sleep(0.1)

    assert state["done"] and not state["error"]
    assert len(state["events"]) >= 1                       # the run streamed steps as it worked
    res = state["result"]
    # The deliverable is whatever the capability produced; what this route
    # owes the caller is the verdict and the reasoning behind it, streamed
    # while the work happened rather than only at the end.
    assert res["accepted"] is True
    assert res["evidence"], "the gate trail must reach the caller"
    assert all("determinism" in g for g in res["evidence"])


def test_http_fails_closed_with_503(tmp_path, monkeypatch):
    from engine.executor import LocalSubprocessExecutor
    from fastapi.testclient import TestClient

    from entropy_os.app import create_app

    monkeypatch.setattr("engine.executor.default_executor", lambda: LocalSubprocessExecutor())
    monkeypatch.setenv("VERITAS_WEDGE_TOKENS", "tok_alice:alice")
    client = TestClient(create_app(data_dir=tmp_path, provider=_provider(), execute=fake_execute()))

    assert client.get("/api/wedge/status").json()["open"] is False
    r = client.post("/api/wedge/submit", json={"goal": "add two numbers"},
                    headers={"Authorization": "Bearer tok_alice"})
    assert r.status_code == 503  # no sandbox -> refused on the host
