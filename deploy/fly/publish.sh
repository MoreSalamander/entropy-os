#!/usr/bin/env bash
# publish.sh — refresh the hosted mirror from THIS machine.
#
# The hosted face shows work that happened here. Everything it serves is a
# file: the engines' outputs and the unified run history. This script restages
# those into deploy/fly/seed/, where the Dockerfile picks them up, and deploys.
#
# Why staging rather than syncing to the running Machine: the image is the only
# thing that survives a redeploy, a rebuild, or a Machine being replaced. State
# pushed onto the Volume would be correct until the next `fly deploy` quietly
# reverted the parts that live in the image, and the two would drift with
# nothing to say which was current.
#
# What this deliberately does NOT touch is the live state on that Volume —
# accounts, the quota ledger, memory a visitor's wedge run created. A stranger
# who signed up and spent a run keeps both across a refresh; that is the point
# of metering it rather than faking it.
#
#   ./deploy/fly/publish.sh              stage, report, deploy
#   ./deploy/fly/publish.sh --stage-only stage and report; deploy yourself
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SEED="$ROOT/deploy/fly/seed"
STORAGE="${ENTROPY_STORAGE:-$ROOT/storage_data}"
APP="$(sed -n 's/^app *= *"\(.*\)".*/\1/p' "$ROOT/deploy/fly/fly.toml" | head -1)"

# member -> the subdirectory of that engine's storage the face actually serves.
# Same four names the composite resolves by convention (composition/artifacts.py
# _CONVENTIONS) and the same ones ONE_ENGINE_ARTIFACTS_* point at in the image,
# so all three agree about what an artifact is.
MEMBERS=(
  "research   reports"
  "software   projects"
  "university lessons"
  "web        sites"
)

# Dependencies and build caches are not what was MADE. The web engine is the
# reason this list matters: its generated sites carry ~415M of node_modules
# around about 10M of actual site. Shipping the dependencies would multiply the
# image by forty for files nobody clicks.
EXCLUDES=(
  --exclude node_modules --exclude .git --exclude .venv
  --exclude __pycache__ --exclude .pytest_cache --exclude .ruff_cache
  --exclude .next --exclude .cache --exclude dist --exclude build
  --exclude '*.pyc' --exclude '.DS_Store'
)

human() { du -sh "$1" 2>/dev/null | cut -f1; }

echo "publishing the mirror from $STORAGE"
echo

# --- how stale was the thing we are replacing --------------------------------
# Printed before anything is overwritten, because the answer stops existing
# once we write. The previous mirror going quietly stale is the bug this
# script exists to fix, so the staleness is stated every single run.
OLD_LOG="$SEED/one_engine_events.jsonl"
if [ -f "$OLD_LOG" ]; then
  OLD_EVENTS="$(wc -l < "$OLD_LOG" | tr -d ' ')"
  if OLD_WHEN="$(date -r "$OLD_LOG" '+%Y-%m-%d %H:%M' 2>/dev/null)"; then
    echo "  previous mirror: $OLD_EVENTS events, staged $OLD_WHEN"
  else
    echo "  previous mirror: $OLD_EVENTS events"
  fi
else
  echo "  previous mirror: none staged"
fi
echo

# --- the engines' outputs ----------------------------------------------------
for row in "${MEMBERS[@]}"; do
  read -r name subdir <<< "$row"
  src="$STORAGE/engines/$name/$subdir"
  dst="$SEED/artifacts/$name/storage_data/$subdir"
  if [ ! -d "$src" ]; then
    echo "  $name: SKIPPED — nothing at $src"
    continue
  fi
  mkdir -p "$dst"
  # --delete so the mirror is a snapshot and not an accumulation: something
  # deleted here has to disappear there, or the hosted face keeps serving work
  # this machine no longer has.
  rsync -a --delete "${EXCLUDES[@]}" "$src/" "$dst/"
  echo "  $name: $(find "$dst" -type f | wc -l | tr -d ' ') files, $(human "$dst")"
done

# --- the unified run history -------------------------------------------------
LOG="$STORAGE/events.jsonl"
if [ -f "$LOG" ]; then
  cp "$LOG" "$SEED/one_engine_events.jsonl"
  echo "  run history: $(wc -l < "$SEED/one_engine_events.jsonl" | tr -d ' ') events, $(human "$SEED/one_engine_events.jsonl")"
else
  echo "  run history: SKIPPED — nothing at $LOG"
fi

echo
echo "staged $(human "$SEED") into deploy/fly/seed"

if [ "${1:-}" = "--stage-only" ]; then
  echo
  echo "not deploying (--stage-only). When ready:"
  echo "  fly deploy -c deploy/fly/fly.toml${APP:+ -a $APP}"
  exit 0
fi

echo
echo "deploying to ${APP:-the app in fly.toml}…"
cd "$ROOT"
fly deploy -c deploy/fly/fly.toml

echo
echo "done. The mirror now shows this machine as of $(date '+%Y-%m-%d %H:%M')."
