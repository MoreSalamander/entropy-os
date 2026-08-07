#!/usr/bin/env bash
# dev.sh — local development bootstrap for the two-repo layout.
#
# Installs veritas (the engine room) editable from the sibling checkout so
# engine changes are live here without reinstall, then this package with its
# dev extras. A clean machine without ../veritas still resolves the declared
# git dependency from pyproject instead.
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
# The web studio's render gate drives a real browser; each playwright version
# wants its own build.
playwright install chromium
echo "entropy-os: ready — run with  .venv/bin/uvicorn entropy_os.app:app --port 8101"
echo "            pre-deploy check:  ./dev.sh smoke  (bare-install boot)"
