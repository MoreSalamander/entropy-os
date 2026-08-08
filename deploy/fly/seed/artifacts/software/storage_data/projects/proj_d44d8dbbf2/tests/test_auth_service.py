"""Generated tests for component auth_service."""


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
