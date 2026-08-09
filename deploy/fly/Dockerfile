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
# The engines are no longer separate installs. They were absorbed into
# entropy-os, so `pip install .` above already put research, software,
# university and web in this image along with the composed engine — one
# environment, one version, nothing to keep in step.
#
# What that deleted is worth recording, because every line of it was load-
# bearing while it existed: research-engine installed first because the other
# three declared it as a dependency and it is not on PyPI; --no-deps on those
# three both to make that resolvable AND to close a supply-chain hole, since
# `code-engine` IS a real PyPI package owned by someone else. There is now no
# `pip install code-engine` to get wrong, because there is no separate
# package to install.
#
# `ruff` stays: the software engine shells out to it as part of its
# verification gate, and nothing else pulls it in.
#
# temporalio stays for the same reason it always did — the composed app
# imports it at module load. No Temporal server runs here, which is the
# honest state: composed runs fall back to inline execution and /health
# reports degraded rather than pretending to durability it does not have.
RUN pip install --no-cache-dir ruff "temporalio>=1.7"

# No topology file is copied any more. It used to differ from the laptop's
# because that one carried repo paths and venv paths for a launcher that
# started each adapter in its own environment; those keys are gone, and what
# is left — four loopback addresses — is identical in both places and ships
# inside the package. A deployment that needs different addresses sets
# ONE_ENGINE_MEMBER_RESEARCH and friends, or points ENTROPY_CONFIG_DIR at a
# directory of its own.
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
