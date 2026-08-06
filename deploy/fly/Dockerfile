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

# The hosting posture baked in. Secrets (ANTHROPIC_API_KEY) come from `fly secrets`, not the image.
# fly.toml [env] can override any of these; they are sane defaults so the image is safe by itself.
ENV ENTROPY_PUBLIC=os \
    ENTROPY_DATA=/data \
    VERITAS_SANDBOX=container \
    VERITAS_MEMORY=sqlite \
    VERITAS_ACCOUNTS=1 \
    VERITAS_MODEL=sonnet \
    VERITAS_DATA=/data

EXPOSE 8101
CMD ["bash", "/opt/entropy-os/deploy/fly/start.sh"]
