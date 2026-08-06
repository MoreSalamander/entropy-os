"""Process-level configuration for the Entropy OS front door.

Entropy OS is the only web process in the two-repo architecture, so the
process concerns live here: .env loading, the data-root anchor, and the
origins of the sibling services the UI talks to. Veritas (the engine room)
is a library and never reads any of this — callers pass paths and providers
into it explicitly.
"""

from __future__ import annotations

import os
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent


def load_dotenv(path: Path | None = None) -> None:
    """Minimal .env loader (KEY=VALUE lines, # comments). Values already in
    the environment win — the file supplies defaults, never overrides."""
    env_path = path or (_ROOT / ".env")
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def default_data_dir() -> Path:
    """The mutable-state root. ENTROPY_DATA env wins; the default is the
    veritas checkout's hub_data sibling directory, because the split
    deliberately moved NO data files — engine stores (runs, memory,
    collector) live where they always did, and Entropy OS points at them.
    """
    env = os.environ.get("ENTROPY_DATA")
    if env:
        return Path(env).expanduser()
    return (_ROOT.parent / "veritas" / "hub_data").resolve()


# The Studio Launchpad origin the home view queries for live project status.
# Browser-side and cross-origin; unreachable is a normal, honest state.
LAUNCHPAD_ORIGIN = os.environ.get("LAUNCHPAD_ORIGIN", "http://localhost:8765")
