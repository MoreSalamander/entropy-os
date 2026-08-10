"""Test wiring: isolated temp database + TestClient per session."""

import os
import tempfile

os.environ["DATABASE_URL"] = (
    "sqlite:///" + tempfile.mkstemp(suffix=".db")[1])

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c
