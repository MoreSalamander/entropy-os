#!/usr/bin/env bash
# smoke_bare_install.sh — prove the front door boots as an INSTALLED PACKAGE.
#
# The hosted box never runs from a source checkout: the Fly image pip-installs
# entropy-os and veritas, so every path the code resolves against its repo root
# lands in site-packages instead. Three hosted boot loops on 2026-08-06 came
# from exactly that gap — vendored products/*/static assets pip didn't ship,
# config/collector_sources.json absent, docs/about.html absent — and none of
# them could reproduce locally because dev installs are editable and the whole
# repo is always there. This smoke rebuilds the hosted condition on purpose:
# both packages installed from freshly built wheels (never -e) into a throwaway
# venv, state anchored to a temp dir, then the exact uvicorn import target is
# loaded and probed. Any import-time or construct-time file dependency that
# leaks back in fails here, loudly, before it fails on Fly.
#
# Usage:
#   ./scripts/smoke_bare_install.sh          # engine from ../veritas, else cloned
#   VERITAS_SRC=/path/to/veritas ...         # engine from an explicit checkout
#   VERITAS_REF=hosted-2026-08-08.2 ...      # engine cloned at the deploy pin
#   ./dev.sh smoke                           # same thing, via the dev entry point
#
# CI-runnable as-is (no checkout of veritas needed — it clones), e.g.:
#   - run: ./scripts/smoke_bare_install.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/entropy-smoke.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT
trap 'echo "SMOKE FAILED at line $LINENO — the bare install does not boot." >&2' ERR

# --- locate the engine source ------------------------------------------------
# Priority mirrors dev.sh: an explicit override, then the sibling checkout, then
# a shallow clone of what the next deploy would actually install. VERITAS_REF
# only applies to the clone — a local checkout is tested as it sits.
VERITAS_REF="${VERITAS_REF:-main}"
if [ -n "${VERITAS_SRC:-}" ]; then
  VERITAS_DIR="$VERITAS_SRC"
elif [ -d "$ROOT/../veritas" ]; then
  VERITAS_DIR="$(cd "$ROOT/../veritas" && pwd)"
else
  echo "[smoke] no local engine checkout — cloning veritas@$VERITAS_REF"
  git clone -q --depth 1 --branch "$VERITAS_REF" \
    https://github.com/MoreSalamander/veritas "$WORK/veritas"
  VERITAS_DIR="$WORK/veritas"
fi
echo "[smoke] engine source: $VERITAS_DIR"

# --- build wheels, install them bare -----------------------------------------
# The venv's own pip does everything, so the host environment contributes
# nothing but a python3. Wheels (not -e, not the source dirs) are the point:
# only what the build backend packages exists at runtime, same as on Fly.
PY_BIN="${PYTHON:-python3}"
"$PY_BIN" -m venv "$WORK/venv"
PIP="$WORK/venv/bin/pip"
PY="$WORK/venv/bin/python"

echo "[smoke] building wheels"
"$PIP" -q wheel --no-deps --wheel-dir "$WORK/wheels" "$VERITAS_DIR" "$ROOT"

echo "[smoke] installing into a bare venv"
"$PIP" -q install "$WORK"/wheels/veritas-*.whl
"$PIP" -q install --no-deps "$WORK"/wheels/entropy_os-*.whl

# entropy-os's own dependencies still come from its wheel metadata — pyproject
# stays the single source of truth — but two kinds are filtered out before
# handing the list back to pip:
#   veritas                       — pinned by URL in pyproject; the local wheel
#                                   above is the one under test, and letting pip
#                                   resolve the URL would silently swap in GitHub.
#   playwright/yt-dlp/trafilatura — runtime capabilities behind lazy seams
#                                   (browser render, transcript fetch). Boot must
#                                   not need them, and proving boot without them
#                                   is itself part of the contract: a module-level
#                                   import of any of these is a regression this
#                                   smoke should catch, not paper over.
"$PY" - "$WORK"/wheels/entropy_os-*.whl >"$WORK/requirements.txt" <<'PYEOF'
import re, sys, zipfile

NOT_NEEDED_TO_BOOT = {"veritas", "playwright", "yt-dlp", "trafilatura"}

with zipfile.ZipFile(sys.argv[1]) as wheel:
    metadata = next(n for n in wheel.namelist() if n.endswith(".dist-info/METADATA"))
    for line in wheel.read(metadata).decode().splitlines():
        if not line.startswith("Requires-Dist:"):
            continue
        requirement = line.split(":", 1)[1].strip()
        if "extra ==" in requirement:  # dev extras never ship to the hosted box
            continue
        name = re.split(r"[ <>=!~@\[;(]", requirement, 1)[0].strip().lower()
        if name.replace("_", "-") not in NOT_NEEDED_TO_BOOT:
            print(requirement)
PYEOF
"$PIP" -q install -r "$WORK/requirements.txt"

# --- the boot probe ----------------------------------------------------------
# Run from the temp dir with -I (isolated: no cwd/PYTHONPATH on sys.path) so a
# source checkout can never quietly satisfy an import the wheel failed to ship.
# The environment is the hosted posture: public os mode, state in a temp dir.
echo "[smoke] boot probe (import + / + /api/orgs)"
(
  cd "$WORK"
  env ENTROPY_PUBLIC=os \
      ENTROPY_DATA="$WORK/data" \
      VERITAS_DATA="$WORK/data" \
      VERITAS_MEMORY=sqlite \
      VERITAS_ACCOUNTS=1 \
      "$PY" -I - <<'PYEOF'
import entropy_os

# Guard the guard: if this resolved from a checkout the whole exercise is void.
assert "site-packages" in entropy_os.__file__, (
    f"entropy_os imported from a source tree, not the wheel: {entropy_os.__file__}"
)

# Boot-loop #1 (2026-08-06): the wheels must carry the vendored container assets.
# Checked directly against the installed packages so a miss names the files
# instead of surfacing as a stack trace three imports deep.
from importlib.resources import files

for pkg in ("products.tutorial", "products.academy"):
    prism = files(pkg) / "static" / "vendor" / "prism"
    shipped = sorted(entry.name for entry in prism.iterdir()) if prism.is_dir() else []
    assert shipped, f"{pkg} wheel shipped no static/vendor/prism assets"

# tutorial's container reads prism AT IMPORT TIME (and entropy_os.app imports it);
# academy's reads lazily at dispense — import both explicitly so each stays covered
# no matter how the hub's own import graph shifts.
import products.tutorial.container
import products.academy.container

# The exact uvicorn target. Module import runs create_app(), so every
# construct-time file dependency fires here — including boot-loop #2, the
# collector sources config now resolved against site-packages, whose absence
# must be a state, not a crash.
import entropy_os.app as hub
from fastapi.testclient import TestClient

client = TestClient(hub.app)

home = client.get("/")
assert home.status_code == 200, f"/ -> {home.status_code}"

orgs_response = client.get("/api/orgs")
assert orgs_response.status_code == 200, f"/api/orgs -> {orgs_response.status_code}"
orgs = orgs_response.json()
assert isinstance(orgs, list) and orgs, "org registry came back empty"
assert all("name" in org and "title" in org for org in orgs), "org entries malformed"

# Boot-loop #3: /about serves the engine checkout's docs/about.html, which a
# bare install may honestly not have — 200 (packaged) and 404 (not) are both
# correct; a 500 means the path leaked back into a crash.
about = client.get("/about")
assert about.status_code in (200, 404), f"/about -> {about.status_code}"

print(f"boot probe: OK — {len(orgs)} orgs, /about -> {about.status_code}")
PYEOF
)

echo "[smoke] PASS — bare install boots (${SECONDS}s)"
