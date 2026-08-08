# Entropy OS — the hosted face, for Fly.io.
#
# A Fly Machine is a Firecracker microVM with its own kernel, so we can run the Docker daemon INSIDE
# it (Docker-in-Docker). The microVM is the hard isolation boundary around the whole tenant-facing app;
# the per-run container the wedge's sandbox spawns is defense-in-depth on top. ContainerExecutor is
# reused unchanged — it just talks to the local daemon that start.sh brings up.
#
# Build context is the entropy-os repo root: from there, `fly deploy -c deploy/fly/fly.toml`.

FROM python:3.12-slim

# docker.io = the daemon (dockerd); docker-cli = the client (/usr/bin/docker) the start script drives —
# it is NOT pulled in under --no-install-recommends, so name it explicitly. fuse-overlayfs gives dockerd
# a working storage driver in nested environments where overlay2 can't mount. git fetches the engine.
RUN apt-get update \
 && apt-get install -y --no-install-recommends docker.io docker-cli fuse-overlayfs ca-certificates git \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/entropy-os
COPY . /opt/entropy-os

# The front door + the engine room. VERITAS_REF pins the engine build (set it to the
# hosted-* tag at ship); the claude extra brings the Anthropic SDK the hosted default
# model needs. Chromium ships for the web slot: the machine renders a
# stranger's page in a real browser so the render/structure/contrast gates
# can rule on it — the vend isn't a vend without the page.
ARG VERITAS_REF=main
RUN pip install --no-cache-dir . \
 && pip install --no-cache-dir --force-reinstall --no-deps \
      "veritas[claude] @ git+https://github.com/MoreSalamander/veritas@${VERITAS_REF}" \
 && pip install --no-cache-dir anthropic playwright \
 && playwright install --with-deps chromium

# The composed engine. Entropy OS reads it over the Universal Engine Contract,
# so it has to actually be here — a snapshot of its output would not be the
# same claim. All five repos are public and their dependencies are light
# (fastapi, httpx, pydantic, networkx, qdrant-client); the three downstream
# engines depend on research-engine, so most of the install is shared.
#
# Installed as packages rather than checkouts: in the image there is one
# environment, so the adapters import their engine directly instead of each
# running inside its own venv the way they do on the laptop.
#
# The install order and --no-deps are load-bearing, not style. The three
# downstream engines declare `research-engine` as a dependency and it does NOT
# exist on PyPI, so resolving them normally fails. They are therefore installed
# with dependencies switched off, against a research-engine already present.
#
# The same flag closes a supply-chain hole: `code-engine` IS a real PyPI
# package owned by someone else. Every engine here must stay pinned to its git
# URL — never relax these into a bare `pip install code-engine`.
#
# `ruff` is the one dependency the --no-deps installs would otherwise miss
# (code-engine runs it as part of its verification gate).
#
# one-engine takes its [orchestration] extra even though no Temporal server
# runs here: the unified app imports temporalio at module load, and the extra
# exists precisely because only the composite may depend on it — engines never
# import Temporal. Installing the client without a server is the honest state;
# composed runs fall back to inline execution and health reports degraded.
ARG ONE_ENGINE_REF=main
RUN pip install --no-cache-dir \
      "research-engine @ git+https://github.com/MoreSalamander/research-engine@main" \
 && pip install --no-cache-dir --no-deps \
      "code-engine @ git+https://github.com/MoreSalamander/code-engine@main" \
      "learn-engine @ git+https://github.com/MoreSalamander/learn-engine@main" \
      "design-engine @ git+https://github.com/MoreSalamander/design-engine@main" \
 && pip install --no-cache-dir ruff \
 && git clone --depth 1 --branch "${ONE_ENGINE_REF}" \
      https://github.com/MoreSalamander/one-engine.git /opt/one-engine \
 && pip install --no-cache-dir -e "/opt/one-engine[orchestration]"

# The laptop's config points at local repo paths and venvs; this one does not.
COPY deploy/fly/one-engine.config.yaml /opt/one-engine/config.yaml
# Real recorded runs, so the composition wing has history to serve on first
# boot. Copied to the Volume by start.sh only when absent — a live machine's
# accumulated log is never overwritten.
COPY deploy/fly/seed/one_engine_events.jsonl /opt/one-engine-seed/events.jsonl
# The outputs those runs actually produced — the research reports, the
# generated projects, the generated sites (~950K, 197 files). Without these a
# visitor can see THAT the composition ran and not WHAT it made. Build caches
# are excluded at staging time; nothing else is trimmed.
COPY deploy/fly/seed/artifacts /opt/one-engine-artifacts

# The hosting posture baked in. Secrets (ANTHROPIC_API_KEY) come from `fly secrets`, not the image.
# fly.toml [env] can override any of these; they are sane defaults so the image is safe by itself.
ENV ENTROPY_PUBLIC=os \
    ENTROPY_DATA=/data \
    VERITAS_SANDBOX=container \
    VERITAS_MEMORY=sqlite \
    VERITAS_ACCOUNTS=1 \
    VERITAS_MODEL=sonnet \
    VERITAS_DATA=/data \
    ONE_ENGINE_URL=http://127.0.0.1:9100 \
    ONE_ENGINE_DATA=/data/one-engine \
    # The engines' storage lives beside each engine on a laptop and nowhere
    # near it in a container, so the artifact roots are repointed rather than
    # inferred. Same conventions, different ground.
    ONE_ENGINE_ARTIFACTS_RESEARCH=/opt/one-engine-artifacts/research/storage_data/reports \
    ONE_ENGINE_ARTIFACTS_SOFTWARE=/opt/one-engine-artifacts/software/storage_data/projects \
    ONE_ENGINE_ARTIFACTS_WEB=/opt/one-engine-artifacts/web/storage_data/sites \
    ONE_ENGINE_ARTIFACTS_UNIVERSITY=/opt/one-engine-artifacts/university/storage_data/lessons

EXPOSE 8101
CMD ["bash", "/opt/entropy-os/deploy/fly/start.sh"]
