"""Generated tests for component gate_outcome_service."""


def test_opportunity_create_and_list(client):
    created = client.post("/opportunitys", json={"hunter_run_id": "sample text", "opportunity_type": "sample text", "created_at": "2026-01-01T00:00:00"})
    assert created.status_code == 201, created.text
    assert created.json()["id"] >= 1
    listed = client.get("/opportunitys")
    assert listed.status_code == 200
    assert any(row["id"] == created.json()["id"] for row in listed.json())


def test_opportunity_missing_returns_404(client):
    res = client.get("/opportunitys/999999")
    assert res.status_code == 404
