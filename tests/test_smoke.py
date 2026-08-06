"""Increment-1 smoke: the front door stands, serves its UI, and anchors state.

The real behavioral contract arrives with the 13 ported HTTP integration
tests in increment 3; until then this guards the factory signature and the
static surface.
"""

from pathlib import Path

from fastapi.testclient import TestClient

from entropy_os.app import create_app


def test_create_app_serves_the_ui(tmp_path: Path) -> None:
    app = create_app(data_dir=tmp_path)
    client = TestClient(app)

    home = client.get("/")
    assert home.status_code == 200
    assert "Veritas" in home.text or "Entropy" in home.text

    theme = client.get("/shared/entropy-theme.css")
    assert theme.status_code == 200

    assert app.state.data_dir == tmp_path


def test_factory_signature_matches_the_hub_contract(tmp_path: Path) -> None:
    # The four keyword seams the integration tests inject through.
    app = create_app(data_dir=tmp_path, provider=None, fetcher=None, search_client=None)
    assert app.title == "Entropy OS"
