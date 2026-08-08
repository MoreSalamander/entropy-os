"""Generated tests for component quiz_service."""


def test_quiz_result_create_and_list(client):
    created = client.post("/quiz_results", json={"user_id": 3, "lesson_id": 3, "score": 1.5})
    assert created.status_code == 201, created.text
    assert created.json()["id"] >= 1
    listed = client.get("/quiz_results")
    assert listed.status_code == 200
    assert any(row["id"] == created.json()["id"] for row in listed.json())


def test_quiz_result_missing_returns_404(client):
    res = client.get("/quiz_results/999999")
    assert res.status_code == 404
