#!/usr/bin/env bash
# Bring the composed system up: four engine adapter servers (each inside its
# OWN venv), the Temporal worker, and the unified system.
#
# Every process is started explicitly with an absolute interpreter path and an
# explicit working directory — a background job inherits neither.
#
#   ./scripts/up.sh          start everything not already running
#   ./scripts/up.sh down     stop everything this script started
#   ./scripts/up.sh status   what is up right now
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN="$ROOT/storage_data/run"
LOGS="$ROOT/storage_data/logs"
VENV="$ROOT/.venv/bin/python"
mkdir -p "$RUN" "$LOGS"

# name repo_dir port
ENGINES=(
  "research   $HOME/MoreSalamander/research-engine  9101"
  "software   $HOME/MoreSalamander/code-engine      9102"
  "university $HOME/MoreSalamander/learn-engine     9103"
  "web        $HOME/MoreSalamander/design-engine    9104"
)

alive() { [[ -f "$RUN/$1.pid" ]] && kill -0 "$(cat "$RUN/$1.pid")" 2>/dev/null; }

start() {  # name command...
  local name="$1"; shift
  if alive "$name"; then echo "  $name already running (pid $(cat "$RUN/$name.pid"))"; return; fi
  "$@" > "$LOGS/$name.log" 2>&1 &
  echo $! > "$RUN/$name.pid"
  echo "  $name → pid $! (log: storage_data/logs/$name.log)"
}

stop_all() {
  for f in "$RUN"/*.pid; do
    [[ -e "$f" ]] || continue
    local name pid; name="$(basename "$f" .pid)"; pid="$(cat "$f")"
    if kill -0 "$pid" 2>/dev/null; then kill "$pid" && echo "  stopped $name ($pid)";
    else echo "  $name was not running"; fi
    rm -f "$f"
  done
}

case "${1:-up}" in
  down) echo "stopping:"; stop_all; exit 0 ;;
  status)
    for f in "$RUN"/*.pid; do
      [[ -e "$f" ]] || continue
      n="$(basename "$f" .pid)"
      alive "$n" && echo "  $n: up (pid $(cat "$f"))" || echo "  $n: DOWN"
    done
    exit 0 ;;
esac

echo "engine adapters (each in its own venv):"
for row in "${ENGINES[@]}"; do
  read -r name repo port <<< "$row"
  py="$repo/.venv/bin/python"
  if [[ ! -x "$py" ]]; then echo "  $name: SKIPPED — no venv at $py"; continue; fi
  # PYTHONPATH, not pip install: one_engine becomes importable inside the
  # engine's interpreter without adding a single package to its venv. The
  # engine repositories and their environments stay exactly as they were.
  start "$name" env PYTHONPATH="$ROOT" "$py" -m one_engine.adapters.serve "$name" --port "$port"
done

echo "orchestration:"
if ! nc -z localhost 7233 2>/dev/null; then
  start temporal-server temporal server start-dev \
    --db-filename "$ROOT/storage_data/temporal-dev.db" \
    --port 7233 --ui-port 8233 --log-level warn
  for _ in $(seq 1 30); do nc -z localhost 7233 2>/dev/null && break; sleep 0.5; done
else
  echo "  temporal server already listening on 7233"
fi
start worker env PYTHONPATH="$ROOT" "$VENV" -m one_engine.orchestration.worker

echo "unified system:"
start unified env PYTHONPATH="$ROOT" "$VENV" -m uvicorn one_engine.app:app \
  --port 9100 --log-level warning

echo
echo "  unified   → http://localhost:9100"
echo "  temporal  → http://localhost:8233"
echo "  datahub   → http://localhost:9002"
