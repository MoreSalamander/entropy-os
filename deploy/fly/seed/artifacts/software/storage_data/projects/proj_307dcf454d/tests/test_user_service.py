"""Generated tests for component user_service."""


def test_user_create_and_list(client):
    created = client.post("/users", json={"username": "sample text", "password_hash": "sample text", "email": "sample text"})
    assert created.status_code == 201, created.text
    assert created.json()["id"] >= 1
    listed = client.get("/users")
    assert listed.status_code == 200
    assert any(row["id"] == created.json()["id"] for row in listed.json())


def test_user_missing_returns_404(client):
    res = client.get("/users/999999")
    assert res.status_code == 404

def test_user_progress_create_and_list(client):
    created = client.post("/user_progresss", json={"user_id": 3, "concept_id": 3, "mastery_level": 1.5})
    assert created.status_code == 201, created.text
    assert created.json()["id"] >= 1
    listed = client.get("/user_progresss")
    assert listed.status_code == 200
    assert any(row["id"] == created.json()["id"] for row in listed.json())


def test_user_progress_missing_returns_404(client):
    res = client.get("/user_progresss/999999")
    assert res.status_code == 404
