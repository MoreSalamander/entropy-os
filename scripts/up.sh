#!/usr/bin/env bash
# Bring the system up: four engine adapter servers, the Temporal worker, and
# the composed engine — all from this repo, all from one interpreter.
#
# The previous version of this script started each adapter inside a different
# repository's virtualenv and bridged them with PYTHONPATH. That was never a
# dependency requirement: the four engines were all >=3.12 with overlapping
# pins, and three of them already depended on the fourth. It was four repos,
# so it became four environments. One repo, one environment.
#
# What did NOT change is how they talk. Every adapter is still its own process
# answering the Universal Engine Contract over HTTP, and the composite still
# reaches its members by URL — so the composite cannot tell whether a member
# is in this repo, on another host, or itself a composite of four. That
# property is the recursion claim, and it survives living in one source tree.
#
#   ./scripts/up.sh          start everything not already running
#   ./scripts/up.sh down     stop everything this script started
#   ./scripts/up.sh status   what is up right now
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN="${ENTROPY_STORAGE:-$ROOT/storage_data}/run"
LOGS="${ENTROPY_STORAGE:-$ROOT/storage_data}/logs"
PY="$ROOT/.venv/bin/python"
mkdir -p "$RUN" "$LOGS"

# Contract member key, and the port its adapter listens on.
ENGINES=(
  "research   9101"
  "software   9102"
  "university 9103"
  "web        9104"
)

alive() { [[ -f "$RUN/$1.pid" ]] && kill -0 "$(cat "$RUN/$1.pid")" 2>/dev/null; }

start() {  # name command...
  local name="$1"; shift
  if alive "$name"; then echo "  $name already running (pid $(cat "$RUN/$name.pid"))"; return; fi
  # An absolute interpreter and an explicit working directory: a background
  # job inherits neither.
  #
  # The redirections sit on the SUBSHELL, not on the command inside it, and
  # stdin comes from /dev/null. Otherwise every server we start inherits this
  # script's stdout, and `./scripts/up.sh | tail` never returns — the pipe
  # stays open as long as any child holds it, which for servers is forever.
  ( cd "$ROOT" && exec "$@" ) > "$LOGS/$name.log" 2>&1 < /dev/null &
  echo $! > "$RUN/$name.pid"
  echo "  $name → pid $! (log: ${LOGS#$ROOT/}/$name.log)"
}

stop_all() {
  shopt -s nullglob
  for f in "$RUN"/*.pid; do
    local name pid; name="$(basename "$f" .pid)"; pid="$(cat "$f")"
    if kill -0 "$pid" 2>/dev/null; then kill "$pid" && echo "  stopped $name ($pid)";
    else echo "  $name was not running"; fi
    rm -f "$f"
  done
}

case "${1:-up}" in
  down) echo "stopping:"; stop_all; exit 0 ;;
  status)
    shopt -s nullglob
    for f in "$RUN"/*.pid; do
      n="$(basename "$f" .pid)"
      alive "$n" && echo "  $n: up (pid $(cat "$f"))" || echo "  $n: DOWN"
    done
    exit 0 ;;
esac

if [[ ! -x "$PY" ]]; then
  echo "no interpreter at $PY — run ./dev.sh first" >&2
  exit 1
fi

echo "engine adapters:"
for row in "${ENGINES[@]}"; do
  read -r name port <<< "$row"
  start "$name" "$PY" -m entropy_os.composition.adapters.serve "$name" --port "$port"
done

echo "orchestration:"
if ! nc -z localhost 7233 2>/dev/null; then
  start temporal-server temporal server start-dev \
    --db-filename "${ENTROPY_STORAGE:-$ROOT/storage_data}/temporal-dev.db" \
    --port 7233 --ui-port 8233 --log-level warn
  for _ in $(seq 1 30); do nc -z localhost 7233 2>/dev/null && break; sleep 0.5; done
else
  echo "  temporal server already listening on 7233"
fi
start worker "$PY" -m entropy_os.composition.orchestration.worker

echo "composed engine:"
start unified "$PY" -m uvicorn entropy_os.composition.app:app \
  --port 9100 --log-level warning

echo
echo "  composed   → http://localhost:9100"
echo "  front door → http://localhost:8101   (.venv/bin/uvicorn entropy_os.app:app --port 8101)"
echo "  temporal   → http://localhost:8233"
echo "  datahub    → http://localhost:9002"
