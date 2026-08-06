#!/usr/bin/env bash
# dev.sh — local development bootstrap for the two-repo layout.
#
# Installs veritas (the engine room) editable from the sibling checkout so
# engine changes are live here without reinstall, then this package with its
# dev extras. A clean machine without ../veritas still resolves the declared
# git dependency from pyproject instead.
set -euo pipefail
cd "$(dirname "$0")"

PY="${PYTHON:-python3}"
[ -d .venv ] || "$PY" -m venv .venv
. .venv/bin/activate
pip -q install --upgrade pip

if [ -d ../veritas ]; then
  pip -q install -e ../veritas
  echo "veritas: editable from ../veritas"
fi
pip -q install -e ".[dev]"
# The web studio's render gate drives a real browser; each playwright version
# wants its own build.
playwright install chromium
echo "entropy-os: ready — run with  .venv/bin/uvicorn entropy_os.app:app --port 8100"
