"""Generated tests for component string_reverser_service."""


def test_string_reversal_request_create_and_list(client):
    created = client.post("/string_reversal_requests", json={"input_string": "sample text"})
    assert created.status_code == 201, created.text
    assert created.json()["id"] >= 1
    listed = client.get("/string_reversal_requests")
    assert listed.status_code == 200
    assert any(row["id"] == created.json()["id"] for row in listed.json())


def test_string_reversal_request_missing_returns_404(client):
    res = client.get("/string_reversal_requests/999999")
    assert res.status_code == 404

def test_string_reversal_response_create_and_list(client):
    created = client.post("/string_reversal_responses", json={"reversed_string": "sample text"})
    assert created.status_code == 201, created.text
    assert created.json()["id"] >= 1
    listed = client.get("/string_reversal_responses")
    assert listed.status_code == 200
    assert any(row["id"] == created.json()["id"] for row in listed.json())


def test_string_reversal_response_missing_returns_404(client):
    res = client.get("/string_reversal_responses/999999")
    assert res.status_code == 404
