"""Generated tests for component phone_formatter_service."""


def test_phone_number_create_and_list(client):
    created = client.post("/phone_numbers", json={"number": "sample text", "country_code": "sample text"})
    assert created.status_code == 201, created.text
    assert created.json()["id"] >= 1
    listed = client.get("/phone_numbers")
    assert listed.status_code == 200
    assert any(row["id"] == created.json()["id"] for row in listed.json())


def test_phone_number_missing_returns_404(client):
    res = client.get("/phone_numbers/999999")
    assert res.status_code == 404
