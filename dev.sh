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

# [claude] on both, so a clone that arrives with an API key and no Ollama works
# on its first model call rather than its second. The Anthropic SDK was
# declared in veritas's `claude` extra and in the Fly image, and in neither
# thing this script installs — so `./dev.sh` produced an environment that
# could select Claude and then fail to import it.
#
# Order matters, and it used to be wrong. This app declares
# `veritas @ git+https://github.com/MoreSalamander/veritas`, so installing it
# re-resolves that URL and replaces any editable veritas with a copy pulled
# from GitHub. Doing the sibling checkout FIRST meant pip silently undid it a
# line later: `engine` and `orgs` came from site-packages, local engine edits
# stopped taking effect, and `repo_root()` pointed at site-packages — which is
# how two tests that read the engine's docs directory started failing with
# nothing in this repo having changed.
#
# So the app goes first and the local override goes last, which is what the
# pyproject comment beside that dependency has always claimed happens.
pip -q install -e ".[dev,claude]"
if [ -d ../veritas ]; then
  pip -q install -e "../veritas[claude]"
  echo "veritas: editable from ../veritas"
fi
# The web engine's render gate drives a real browser; each playwright version
# wants its own build.
playwright install chromium
echo "entropy-os: ready"
echo "  front door → .venv/bin/uvicorn entropy_os.app:app --port 8101"
echo "  engines    → ./scripts/up.sh        (adapters, worker, composed engine)"
echo "  tests      → .venv/bin/pytest -q"
echo "  pre-deploy → ./dev.sh smoke         (bare-install boot)"
