"""Generated tests for component dataset_service."""



def test_dataset_missing_returns_404(client):
    res = client.get("/datasets/{id}")
    assert res.status_code == 404
