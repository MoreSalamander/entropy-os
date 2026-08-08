"""The wedge interview: the engine asks until the spec can pass, the visitor's
take is the human tier, and the meter counts the build."""

import json
import time
from pathlib import Path

from engine.model import ScriptedProvider
from fastapi.testclient import TestClient

from entropy_os.app import create_app

SPEC = {
    "title": "Night Owls",
    "description": "a study group page",
    "required_elements": ["h1", "button"],
    "aesthetics": {"theme": "dark", "min_contrast": 4.5, "fonts": ["monospace"], "palette": ["#0a0a0a", "#ffffff"]},
}
GOOD = ("<!doctype "
    "html><html><head><style>body{background:#0a0a0a;color:#ffffff;font-family:monospace}"
        "button{background:#0a0a0a;color:#ffffff;font-family:monospace}</style></head>"
        "<body><h1>Night Owls</h1><button>Join</button></body></html>")


def _provider() -> ScriptedProvider:
    return ScriptedProvider({"interviewer": json.dumps({"spec": SPEC}), "web-developer": GOOD})


def _auth(client: TestClient) -> dict:
    client.post("/api/auth/signup", json={"username": "ivtester", "password": "pw-ivtester-1"})
    token = client.post("/api/auth/login",
                        json={"username": "ivtester", "password": "pw-ivtester-1"}).json()["token"]
    return {"Authorization": f"Bearer {token}"}


def _poll(client: TestClient, token: str, until, timeout: float = 30.0) -> dict:
    deadline = time.time() + timeout
    state: dict = {}
    while time.time() < deadline:
        state = client.get(f"/api/wedge/create/{token}").json()
        if until(state):
            return state
        time.sleep(0.1)
    raise AssertionError(f"session never reached the awaited phase; last={state}")


def test_wedge_interview_builds_and_visitor_take_is_the_human_tier(tmp_path: Path,
                                                                   monkeypatch) -> None:
    monkeypatch.setenv("VERITAS_ACCOUNTS", "1")
    client = TestClient(create_app(data_dir=tmp_path, provider=_provider()))
    headers = _auth(client)

    token = client.post("/api/wedge/create/start", json={"goal": "a page"},
                        headers=headers).json()["token"]
    reviewing = _poll(client, token, lambda s: s.get("phase") == "reviewing")
    assert reviewing["page_html"] and any(g["passed"] for g in reviewing["trust"]["machine"])

    client.post(f"/api/wedge/create/{token}/review", json={"approved": True, "feedback": ""})
    done = _poll(client, token, lambda s: s.get("phase") == "done")
    assert done["result"] and done["result"]["accepted"]


def test_wedge_interview_requires_identity(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("VERITAS_ACCOUNTS", "1")
    client = TestClient(create_app(data_dir=tmp_path, provider=_provider()))
    assert client.post("/api/wedge/create/start", json={"goal": "x"}).status_code == 401
