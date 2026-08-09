"""Generated tests for component gate_outcome_service."""


def test_hunter_run_outcome_create_and_list(client):
    created = client.post("/hunter_run_outcomes", json={"hunter_run_id": 3, "opportunity_type": "sample text", "model_invoked": "sample text", "outcome": True})
    assert created.status_code == 201, created.text
    assert created.json()["id"] >= 1
    listed = client.get("/hunter_run_outcomes")
    assert listed.status_code == 200
    assert any(row["id"] == created.json()["id"] for row in listed.json())


def test_hunter_run_outcome_missing_returns_404(client):
    res = client.get("/hunter_run_outcomes/999999")
    assert res.status_code == 404

def test_opportunity_create_and_list(client):
    created = client.post("/opportunitys", json={"opportunity_type": "sample text", "model_invoked": "sample text"})
    assert created.status_code == 201, created.text
    assert created.json()["id"] >= 1
    listed = client.get("/opportunitys")
    assert listed.status_code == 200
    assert any(row["id"] == created.json()["id"] for row in listed.json())


def test_opportunity_missing_returns_404(client):
    res = client.get("/opportunitys/999999")
    assert res.status_code == 404
