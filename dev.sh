#!/usr/bin/env bash
# dev.sh — local development bootstrap.
#
# One environment for the front door, the composed engine, and the four
# engines it composes. Veritas (the engine room) is still a separate package,
# installed editable from the sibling checkout so engine-room changes are live
# here without a reinstall; a clean machine without ../veritas resolves the
# declared git dependency from pyproject instead.
set -euo pipefail
cd "$(dirname "$0")"

# `./dev.sh smoke` — prove the app boots as an INSTALLED PACKAGE (wheels in a
# throwaway venv, no checkout on sys.path): the hosted boot-loop class of
# 2026-08-06. Run it before cutting a deploy; details in the script.
if [ "${1:-}" = "smoke" ]; then
  exec scripts/smoke_bare_install.sh
fi

PY="${PYTHON:-python3}"
[ -d .venv ] || "$PY" -m venv .venv
. .venv/bin/activate
pip -q install --upgrade pip

if [ -d ../veritas ]; then
  pip -q install -e ../veritas
  echo "veritas: editable from ../veritas"
fi
pip -q install -e ".[dev]"
# The web engine's render gate drives a real browser; each playwright version
# wants its own build.
playwright install chromium
echo "entropy-os: ready"
echo "  front door → .venv/bin/uvicorn entropy_os.app:app --port 8101"
echo "  engines    → ./scripts/up.sh        (adapters, worker, composed engine)"
echo "  tests      → .venv/bin/pytest -q"
echo "  pre-deploy → ./dev.sh smoke         (bare-install boot)"
