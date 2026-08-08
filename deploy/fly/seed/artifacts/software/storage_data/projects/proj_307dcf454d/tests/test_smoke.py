"""Smoke: app boots, health answers, schema is reachable."""


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_openapi_lists_routes(client):
    paths = client.get("/openapi.json").json()["paths"]
    assert "/health" in paths
