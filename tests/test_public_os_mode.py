"""ENTROPY_PUBLIC=os — the hosted face: open reads, metered wedge, closed writes."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from entropy_os.app import create_app


@pytest.fixture
def os_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("ENTROPY_PUBLIC", "os")
    return TestClient(create_app(data_dir=tmp_path))


@pytest.mark.parametrize("path", [
    "/", "/about", "/wedge", "/try",
    "/api/orgs", "/api/org-groups", "/api/dashboard", "/api/models",
    "/api/runs", "/api/memory", "/api/commons",
    "/api/tutorial/products", "/api/academy/products",
])
def test_read_surface_is_open(os_client: TestClient, path: str) -> None:
    assert os_client.get(path).status_code == 200


@pytest.mark.parametrize("method,path", [
    ("post", "/api/runs"),               # spending compute is never anonymous
    ("post", "/api/runs/start"),
    ("post", "/api/route"),              # an unauthenticated token burner
    ("post", "/api/chat"),
    ("post", "/api/commons"),
    ("post", "/api/commons/search"),
    ("post", "/api/create/start"),
    ("post", "/api/produce/start"),
    ("post", "/api/plan/start"),
    ("post", "/api/brief/start"),
    ("post", "/api/bench/start"),
    ("post", "/api/tune/start"),
    ("post", "/api/tutorial/start"),
    ("post", "/api/collector/collect"),
    ("get", "/api/collector/pending"),
    ("get", "/api/keytracker/keys"),
    ("post", "/api/memory/vault/sync"),
])
def test_everything_else_is_closed(os_client: TestClient, method: str, path: str) -> None:
    kwargs = {"json": {}} if method != "get" else {}
    assert os_client.request(method.upper(), path, **kwargs).status_code == 404


def test_wedge_stays_metered_not_open(os_client: TestClient) -> None:
    # The metered tier is reachable — and still demands its own auth.
    assert os_client.get("/api/wedge/status").status_code == 200
    r = os_client.post("/api/wedge/submit", json={"goal": "x"})
    assert r.status_code in (401, 403, 422)  # never 404: reachable, refused by auth


def test_face_serves_home_not_wedge_redirect(os_client: TestClient) -> None:
    r = os_client.get("/", follow_redirects=False)
    assert r.status_code == 200  # the face IS the front page in os mode


def test_legacy_mode_still_wedge_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENTROPY_PUBLIC", "1")
    client = TestClient(create_app(data_dir=tmp_path))
    assert client.get("/api/orgs").status_code == 404
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 307 and r.headers["location"] == "/wedge"
