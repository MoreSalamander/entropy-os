#!/usr/bin/env bash
# Entrypoint for the Fly Machine: bring up the Docker daemon (the sandbox needs it), then the app.
set -euo pipefail

DATA="${VERITAS_DATA:-/data}"
mkdir -p "$DATA"

# Start dockerd inside the microVM. We only ever run `--network none` sandboxes, so we skip the bridge
# and iptables setup entirely — fewer privileges needed, and isolation is unaffected. Docker's data
# lives on the mounted Fly Volume so pulled images and layers survive restarts.
dockerd \
  --data-root="$DATA/docker" \
  --bridge=none \
  --iptables=false \
  >/var/log/dockerd.log 2>&1 &

# Wait for the daemon to answer before we accept any traffic.
for _ in $(seq 1 60); do
  if docker info >/dev/null 2>&1; then break; fi
  sleep 1
done
if ! docker info >/dev/null 2>&1; then
  echo "FATAL: dockerd did not come up; the wedge fails closed without a sandbox." >&2
  tail -n 40 /var/log/dockerd.log >&2 || true
  exit 1
fi

# Pre-pull the sandbox image (cached on the Volume after the first boot, so this is a no-op later).
docker image inspect python:3.12-slim >/dev/null 2>&1 || docker pull python:3.12-slim

# Stock the Vending Machine's premade shelf (idempotent, seed-if-missing by
# record id — a live box's accumulated memory is never overwritten). An empty
# shelf is a display problem, not a safety problem, so a seeding failure warns
# and lets the front door open anyway.
python /opt/entropy-os/scripts/seed_shelf.py || echo "WARN: shelf seeding failed; the premade shelf may be empty" >&2

# --- one-engine: the composed engine Entropy OS reads over the contract ------
# Four adapter servers plus the composite, all on loopback. They are NOT
# published by fly.toml's http_service, so nothing here is reachable from the
# internet — only the front door in this same Machine can read them.
#
# Deliberately no Temporal: composed EXECUTION is closed on the hosted face,
# and reading what already ran needs none of it. The composite reports itself
# degraded rather than pretending otherwise.
ONE_ENGINE_DATA="${ONE_ENGINE_DATA:-$DATA/one-engine}"
mkdir -p "$ONE_ENGINE_DATA"

# The engines' own accumulated state — knowledge graphs, vector indexes,
# generated projects, learner profiles. This must be on the Volume: the
# default is a directory inside the installed package, which here is an image
# layer, so a restart would discard everything the engines had learned while
# the front door came back looking perfectly healthy.
ENTROPY_STORAGE="${ENTROPY_STORAGE:-$DATA/engines}"
export ENTROPY_STORAGE
mkdir -p "$ENTROPY_STORAGE"
echo "engines: state on ${ENTROPY_STORAGE}"

# Seed the recorded run history once. Seed-if-missing, never overwrite: a live
# machine's accumulated log outranks whatever shipped in the image.
if [ ! -f "$ONE_ENGINE_DATA/events.jsonl" ] && [ -f /opt/one-engine-seed/events.jsonl ]; then
  cp /opt/one-engine-seed/events.jsonl "$ONE_ENGINE_DATA/events.jsonl"
  echo "one-engine: seeded run history ($(wc -l < "$ONE_ENGINE_DATA/events.jsonl") events)"
fi

start_member() {  # name port
  python -m entropy_os.composition.adapters.serve "$1" --host 127.0.0.1 --port "$2" \
    >"/var/log/one-engine-$1.log" 2>&1 &
  echo "one-engine: $1 adapter -> 127.0.0.1:$2 (pid $!)"
}
start_member research   9101
start_member software   9102
start_member university 9103
start_member web        9104

python -m uvicorn entropy_os.composition.app:app --host 127.0.0.1 --port 9100 --log-level warning \
  >/var/log/one-engine-unified.log 2>&1 &
echo "one-engine: unified -> 127.0.0.1:9100 (pid $!)"

# Best effort by design: the composition wing degrades honestly and names the
# address it tried, so a slow or failed member must not stop the front door
# from opening.
for _ in $(seq 1 30); do
  if python -c "import urllib.request,sys; urllib.request.urlopen('http://127.0.0.1:9100/health', timeout=2)" 2>/dev/null; then
    echo "one-engine: unified answering"; break
  fi
  sleep 1
done

# Hand off to the app. Bind to all interfaces inside the microVM; Fly's proxy terminates TLS in front.
exec uvicorn entropy_os.app:app --host 0.0.0.0 --port 8101
