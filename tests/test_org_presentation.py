"""The era split — the face's wing assignment — rides the /api/orgs merge."""

from pathlib import Path

from fastapi.testclient import TestClient

from entropy_os.app import create_app


def test_orgs_carry_era_and_hunters_are_datahub(tmp_path: Path) -> None:
    client = TestClient(create_app(data_dir=tmp_path))
    orgs = {o["name"]: o for o in client.get("/api/orgs").json()}

    hunters = {"crypto_hunter", "collectible_hunter", "free_money_hunter", "hackathon_hunter"}
    assert hunters <= set(orgs), "all four Hunter engines are registered"
    for name in hunters:
        assert orgs[name]["era"] == "datahub"
    for name in ("software", "web", "research", "production", "empirical"):
        assert orgs[name]["era"] == "inhouse"

    assert orgs["hackathon_hunter"]["color"] == "#e85c5c"
    assert orgs["hackathon_hunter"]["repo_url"].endswith("/hackathon-hunter")
