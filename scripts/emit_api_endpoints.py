#!/usr/bin/env python
"""Publish the front door's real route surface to DataHub as APIEndpoint entities.

After the split, the API-endpoint catalog is entropy-os's to emit: veritas's
engineering emitter takes the FastAPI app as a parameter and skips honestly
without one. This runner passes our app in.

Run with the DataHub SDK interpreter (acryl-datahub needs Python ≤3.13), with
both repos importable — from the veritas checkout:

    PYTHONPATH=.:../entropy-os .venv-datahub/bin/python \
        ../entropy-os/scripts/emit_api_endpoints.py
"""

from __future__ import annotations

import sys

from datahub.emitter.rest_emitter import DatahubRestEmitter

from orgs.datahub_engineering_emit import GMS_SERVER, _emit_api_endpoints

from entropy_os.app import create_app


def main() -> None:
    emitter = DatahubRestEmitter(gms_server=GMS_SERVER)
    urns = _emit_api_endpoints(
        emitter,
        fastapi_app=create_app(),
        route_description="Real Entropy OS front-door FastAPI route.",
    )
    print(f"emitted {len(urns)} APIEndpoint entities", file=sys.stderr)


if __name__ == "__main__":
    main()
