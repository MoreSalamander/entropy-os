"""Generated tests for component quiz_service."""



def test_quiz_missing_returns_404(client):
    res = client.get("/quizzes/999999")
    assert res.status_code == 404
