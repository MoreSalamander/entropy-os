"""Generated tests for component curriculum_service."""


def test_concept_create_and_list(client):
    created = client.post("/concepts", json={"title": "sample text", "description": "longer sample body"})
    assert created.status_code == 201, created.text
    assert created.json()["id"] >= 1
    listed = client.get("/concepts")
    assert listed.status_code == 200
    assert any(row["id"] == created.json()["id"] for row in listed.json())


def test_concept_missing_returns_404(client):
    res = client.get("/concepts/999999")
    assert res.status_code == 404

def test_user_create_and_list(client):
    created = client.post("/users", json={"username": "sample text", "email": "sample text", "password_hash": "sample text"})
    assert created.status_code == 201, created.text
    assert created.json()["id"] >= 1
    listed = client.get("/users")
    assert listed.status_code == 200
    assert any(row["id"] == created.json()["id"] for row in listed.json())


def test_user_missing_returns_404(client):
    res = client.get("/users/999999")
    assert res.status_code == 404

def test_quiz_result_create_and_list(client):
    created = client.post("/quiz_results", json={"concept_id": 3, "user_id": 3, "score": 1.5})
    assert created.status_code == 201, created.text
    assert created.json()["id"] >= 1
    listed = client.get("/quiz_results")
    assert listed.status_code == 200
    assert any(row["id"] == created.json()["id"] for row in listed.json())


def test_quiz_result_missing_returns_404(client):
    res = client.get("/quiz_results/999999")
    assert res.status_code == 404
