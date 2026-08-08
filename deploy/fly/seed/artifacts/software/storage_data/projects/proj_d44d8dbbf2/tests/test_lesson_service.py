"""Generated tests for component lesson_service."""



def test_lesson_missing_returns_404(client):
    res = client.get("/lessons/999999")
    assert res.status_code == 404

def test_quiz_create_and_list(client):
    created = client.post("/quizs", json={"title": "sample text", "description": "longer sample body", "questions": "longer sample body"})
    assert created.status_code == 201, created.text
    assert created.json()["id"] >= 1
    listed = client.get("/quizs")
    assert listed.status_code == 200
    assert any(row["id"] == created.json()["id"] for row in listed.json())


def test_quiz_missing_returns_404(client):
    res = client.get("/quizs/999999")
    assert res.status_code == 404
