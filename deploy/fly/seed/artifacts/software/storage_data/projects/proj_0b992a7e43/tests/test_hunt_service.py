"""Generated tests for component hunt_service."""


def test_hunter_run_create_and_list(client):
    created = client.post("/hunter_runs", json={"hunter_id": "sample text", "location": "sample text", "timestamp": "2026-01-01T00:00:00"})
    assert created.status_code == 201, created.text
    assert created.json()["id"] >= 1
    listed = client.get("/hunter_runs")
    assert listed.status_code == 200
    assert any(row["id"] == created.json()["id"] for row in listed.json())


def test_hunter_run_missing_returns_404(client):
    res = client.get("/hunter_runs/999999")
    assert res.status_code == 404
