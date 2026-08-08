"""Serve one engine's contract surface from inside that engine's own venv.

    cd <one-engine repo> is NOT required — paths come from config.yaml:

    /path/to/research-engine/.venv/bin/python -m one_engine.adapters.serve research

The process reproduces how the engine is normally run: its repository root
goes on sys.path and becomes the working directory. That is the engines'
actual deployment model — none of the four installs its own package into its
venv; each resolves it from the repo root, and each resolves config and
storage relative to that root. one_engine reaches the interpreter through
PYTHONPATH, so nothing is installed and the engine repositories and their
environments are left exactly as they were.
"""

from __future__ import annotations

import argparse
import os
import sys

import uvicorn

from ..config import load_config
from ..contract.http import build_engine_app
from . import ADAPTERS


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("engine", choices=sorted(ADAPTERS))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=0,
                        help="default: the port assigned in config.yaml")
    args = parser.parse_args()

    cfg = load_config()
    member = cfg.engines[args.engine]
    if member.repo:
        # Order matters: sys.path is fixed at interpreter startup, so
        # chdir alone would NOT make the engine's package importable.
        sys.path.insert(0, member.repo)
        os.chdir(member.repo)
    port = args.port or member.port

    adapter = ADAPTERS[args.engine]()
    app = build_engine_app(adapter, title=f"{adapter.name} · contract")
    uvicorn.run(app, host=args.host, port=port, log_level="warning")


if __name__ == "__main__":
    main()
