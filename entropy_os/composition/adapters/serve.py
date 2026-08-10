"""Serve one engine's contract surface as its own process.

    python -m entropy_os.composition.adapters.serve research

Each engine answers the Universal Engine Contract over HTTP, exactly as it
did when it lived in its own repository — the composite still reaches it by
URL and still cannot tell what is behind that URL. What changed is only what
had to happen before the server could start: this module used to insert a
foreign repository root onto sys.path and chdir into it, because each engine
resolved its own package, config and storage relative to a root it owned.
Absorbed into Entropy OS, the engines are ordinary importable modules and
their storage is addressed through `entropy_os.paths`, so the process starts
with no path surgery at all.

The port still comes from the topology file when not given explicitly: which
address a member listens on is deployment configuration, and the composite
reads the same file to know where to find it.
"""

from __future__ import annotations

import argparse

import uvicorn

from ...config import load_dotenv
from ..config import load_config
from ..contract.http import build_engine_app
from . import ADAPTERS


def main() -> None:
    # The engines are the processes that actually call out — to Wikipedia, to
    # Crossref, to every keyed source — and until now only the front door read
    # `.env`. So a source key or a contact address put there was visible to the
    # one process that never uses it and invisible to the four that do, and the
    # symptom was a status table full of `needs_key` for keys that were sitting
    # in the file all along.
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("engine", choices=sorted(ADAPTERS))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=0,
                        help="default: the port assigned in config/composition.yaml")
    args = parser.parse_args()

    cfg = load_config()
    member = cfg.engines[args.engine]
    port = args.port or member.port

    adapter = ADAPTERS[args.engine]()
    app = build_engine_app(adapter, title=f"{adapter.name} · contract")
    uvicorn.run(app, host=args.host, port=port, log_level="warning")


if __name__ == "__main__":
    main()
