"""Generated tests for component country_code_repository."""


def test_country_code_create_and_list(client):
    created = client.post("/country_codes", json={"code": "sample text", "description": "longer sample body"})
    assert created.status_code == 201, created.text
    assert created.json()["id"] >= 1
    listed = client.get("/country_codes")
    assert listed.status_code == 200
    assert any(row["id"] == created.json()["id"] for row in listed.json())


def test_country_code_missing_returns_404(client):
    res = client.get("/country_codes/999999")
    assert res.status_code == 404
