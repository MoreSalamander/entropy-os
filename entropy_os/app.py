"""The Entropy OS application — the front door of the whole platform.

Increment 1 of the split: this app serves the UI (moved verbatim from
veritas hub/static) and nothing else; every /api/* route still lives in
veritas's hub during the dual-running phase and ports over group by group.

The factory signature matches veritas's `hub.app.create_app` exactly and on
purpose — the 13 HTTP integration tests that define the behavioral contract
port here with only their import line changed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from entropy_os.config import default_data_dir, load_dotenv

_STATIC = Path(__file__).resolve().parent / "static"


def create_app(
    data_dir: Path | str | None = None,
    provider: Any | None = None,
    fetcher: Any | None = None,
    search_client: Any | None = None,
) -> FastAPI:
    load_dotenv()
    data = Path(data_dir) if data_dir else default_data_dir()

    app = FastAPI(title="Entropy OS")
    # Stashed for routers as they port over (increment 3); the AppState
    # dataclass replaces veritas's create_app closure web.
    app.state.data_dir = data
    app.state.provider = provider
    app.state.fetcher = fetcher
    app.state.search_client = search_client

    @app.get("/")
    def home() -> FileResponse:
        return FileResponse(_STATIC / "index.html")

    app.mount("/static", StaticFiles(directory=_STATIC), name="static")
    app.mount("/shared", StaticFiles(directory=_STATIC / "shared"), name="shared")

    return app
