"""The vending machine: a gated artifact becomes an image; copies get dispensed.

This is where the artifact-locality problem resolves. An `ArtifactRef` is a
filesystem path on whichever machine ran that engine, which makes it useless
to anyone else the moment the members stop sharing a disk. An image tag is not
— it is location-independent, and a dispensed copy is reachable over HTTP
wherever it runs.

**The admission gate is the scaffold.** Veritas's rule is that a product's
admission into the vending machine is its own verification model, not a new
judgment invented at packaging time. one-engine already has that model: the
composition gates. So an artifact is packageable only if the gates that judged
its stage said proceed — which is what makes "stocks only gate-verified
builds" a fact about the code rather than a slogan.

What each artifact kind becomes:

  report, lesson   a static page on nginx — the content is already a document
  project          the project's OWN generated Dockerfile, built as-is
  site             refused, honestly: Next.js source needs a node build step
                   that does not exist here yet, and shipping an unbuilt
                   source tree as though it were a running site would be a lie
"""

from __future__ import annotations

import html
import hashlib
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

from ..contract import ArtifactRef
from ..scaffold import StageJudgment
from .docker import (
    DispensedCopy,
    VendingError,
    available,
    build,
    dispense,
    image_exists,
)

# Artifact kinds this machine can package, and how.
STATIC_KINDS = ("report", "lesson")
NATIVE_DOCKERFILE_KINDS = ("project",)
# A generated site is source, not a bundle — but the build it needs is a
# node toolchain, and a container is exactly where a toolchain you do not
# have locally belongs. The refusal was honest when there was no strategy;
# writing one is better than keeping the apology.
NODE_BUILD_KINDS = ("site",)

UNSUPPORTED_KINDS = {
    "sidecar": "a sidecar is a model of another artifact, not a product",
}

# What each kind serves on, inside its container. A generated FastAPI project
# declares 8000 in its own Dockerfile; Next.js serves 3000; a static page is
# nginx on 80. Guessing one number for all of them dispenses a container that
# is running perfectly and answering nothing.
CONTAINER_PORTS = {"project": 8000, "site": 3000}
DEFAULT_CONTAINER_PORT = 80

# Written for a generated Next.js tree that has package.json and a build
# script. `npm install` rather than `ci`: these trees are generated, and a
# lockfile is not guaranteed to be there.
NEXT_DOCKERFILE = """FROM node:20-alpine
WORKDIR /app
ARG NEXT_BASE_PATH=""
ENV NEXT_BASE_PATH=$NEXT_BASE_PATH
COPY package*.json ./
RUN npm install --no-audit --no-fund
COPY . .
__REBASE__
RUN npm run build
EXPOSE 3000
ENV HOSTNAME=0.0.0.0 PORT=3000
CMD ["npm", "start"]
"""


@dataclass(frozen=True)
class StockItem:
    """One packaged, dispensable product."""
    image: str
    kind: str
    title: str
    source_path: str
    # The port the product listens on inside its container.
    container_port: int = DEFAULT_CONTAINER_PORT
    # A stable id for this image's copy, so a site can be BUILT knowing the
    # path it will be served under. See dispense_key().
    dispense_key: str = ""
    # True when this press only had to run an image that already existed.
    warm: bool = False
    # True when the app was built knowing its URL prefix and therefore expects
    # to receive it. A proxy in front must forward the path untouched; stripping
    # it turns the app's own home page into its 404.
    owns_prefix: bool = False


def image_tag(objective_id: str, kind: str, name: str) -> str:
    """A readable tag beats a hash for anyone reading `docker images`."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40] or "item"
    return f"one-engine/{kind}-{slug}:{objective_id}"


def dispense_key(tag: str) -> str:
    """A stable id for "the copy of this image", derived from the tag alone.

    Copies are normally addressed by container id, which is the honest name
    for a disposable thing. A Next.js site cannot use it: `basePath` is
    compiled into the bundle at BUILD time, and a container id does not exist
    until run time. Anything built without knowing its own prefix asks for
    `/_next/...` at the origin root and 404s — the page arrives and its
    stylesheet does not.

    So the prefix has to be knowable before the build, which means derived
    from the image rather than from the container. Same artifact, same
    objective, same tag, same path — which also means the URL for a given site
    stays the same across dispenses instead of moving every time.
    """
    return hashlib.sha256(tag.encode()).hexdigest()[:32]


# Injected into a generated Next.js tree at IMAGE BUILD time, never into the
# source: a generated site is the record of what was generated, and packaging
# must not edit that record. The wrapper re-exports the tree's own config with
# assetPrefix added, so the site's security headers and everything else it
# configured survive.
#
# BOTH basePath and assetPrefix, and the proxy stops stripping the prefix for
# these copies. The two-step it took to get here is worth recording.
#
# assetPrefix alone fixed the bundle and left the navigation broken: the site
# still emitted `<a href="/product">` and `<a href="/">`, which are absolute and
# so ignore the `<base>` tag entirely. Clicking the site's own logo left the
# copy and landed on the Entropy front page.
#
# basePath alone broke the opposite half: Next then expects every request to
# arrive carrying the prefix, and a proxy that strips it turns the site's home
# page into a Next 404.
#
# So: set both, and let the app own its prefix — forward the path untouched, as
# Next expects when deployed under a subpath. dispensed.py said a generated app
# that needs to own the root "needs its own hostname"; this is the cheaper half
# of that observation, which is that it can own a PREFIX instead, as long as
# nothing in front of it lies about what the prefix is.
_NEXT_REBASE = """\
RUN if [ -n "$NEXT_BASE_PATH" ]; then \\
      for f in next.config.mjs next.config.js; do \\
        if [ -f "$f" ]; then mv "$f" "next.config.orig.${f##*.}"; break; fi; \\
      done; \\
      if [ ! -f next.config.orig.mjs ] && [ ! -f next.config.orig.js ]; then \\
        echo 'export default {};' > next.config.orig.mjs; \\
      fi; \\
      orig=$(ls next.config.orig.* | head -1); \\
      printf 'import base from "./%s";\\nexport default { ...base, basePath: "%s", assetPrefix: "%s" };\\n' \\
        "$orig" "$NEXT_BASE_PATH" "$NEXT_BASE_PATH" > next.config.mjs; \\
    fi
"""


def packageable(artifact: ArtifactRef) -> tuple[bool, str]:
    """Whether this kind can be packaged, and why not when it cannot."""
    if artifact.kind in UNSUPPORTED_KINDS:
        return False, UNSUPPORTED_KINDS[artifact.kind]
    if artifact.kind not in STATIC_KINDS + NATIVE_DOCKERFILE_KINDS + NODE_BUILD_KINDS:
        return False, f"no packaging strategy for kind {artifact.kind!r}"
    if not artifact.path or not Path(artifact.path).exists():
        return False, f"artifact path does not exist: {artifact.path!r}"
    return True, ""


def admitted(judgment: StageJudgment) -> tuple[bool, str]:
    """The gate. An artifact whose stage was blocked or held is not stock.

    This is the whole point of borrowing Veritas's rule: the machine does not
    form a second opinion about quality, it reads the verdict the scaffold
    already reached.
    """
    if judgment.action != "proceed":
        failed = ", ".join(v.gate for v in judgment.failed)
        return False, (f"stage {judgment.stage_seq} ({judgment.engine}) was "
                       f"{judgment.action}ed by {failed}")
    return True, ""


# --------------------------------------------------------------------------- #
# packaging
# --------------------------------------------------------------------------- #

_PAGE = """<!doctype html>
<meta charset="utf-8"><title>{title}</title>
<style>
 body{{margin:0;background:#0b0d10;color:#e7edf3;
      font:16px/1.65 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}}
 main{{max-width:46em;margin:0 auto;padding:44px 24px 80px}}
 pre{{background:#12161b;border:1px solid #1e2630;border-radius:9px;
      padding:14px 16px;overflow-x:auto;font-size:13px}}
 h1{{font-size:28px;letter-spacing:-.02em}} a{{color:#7aa2f7}}
 .prov{{margin-top:44px;padding-top:16px;border-top:1px solid #1e2630;
        color:#8a99a8;font-size:13px}}
</style>
<main>{body}
<div class="prov">Dispensed by one-engine · {provenance}</div></main>
"""


def _static_page(artifact: ArtifactRef, provenance: str) -> str:
    """Render a document artifact into one self-contained page.

    Markdown is presented as preformatted text rather than converted: this
    module has no markdown dependency, and showing the source honestly beats
    a half-correct rendering. A lesson that already ships HTML is used as-is.
    """
    path = Path(artifact.path)
    if path.suffix == ".html":
        return path.read_text(encoding="utf-8", errors="replace")
    sibling_html = path.with_suffix(".html")
    if sibling_html.exists():
        return sibling_html.read_text(encoding="utf-8", errors="replace")
    text = path.read_text(encoding="utf-8", errors="replace")
    return _PAGE.format(title=html.escape(artifact.description or path.name),
                        body=f"<pre>{html.escape(text)}</pre>",
                        provenance=html.escape(provenance))


def package(artifact: ArtifactRef, objective_id: str,
            judgment: StageJudgment | None = None,
            force: bool = False) -> StockItem:
    """Build an image for one artifact. Raises VendingError with the reason.

    Order of refusal is deliberate: the gate is checked before Docker, so a
    rejected artifact is reported as rejected rather than as an infrastructure
    problem.
    """
    if judgment is not None:
        ok, why = admitted(judgment)
        if not ok:
            raise VendingError(f"not stock: {why}")

    ok, why = packageable(artifact)
    if not ok:
        raise VendingError(f"cannot package: {why}")

    docker_ok, status = available()
    if not docker_ok:
        raise VendingError(f"refusing to dispense unisolated: {status}")

    path = Path(artifact.path)
    name = artifact.description or path.name
    tag = image_tag(objective_id, artifact.kind, path.name)
    key = dispense_key(tag)
    provenance = f"{artifact.kind} from objective {objective_id}"

    # Already built? Then this press is a `docker run`, like the premade racks.
    # Deliberately checked after the gate and after Docker, so a rejected
    # artifact is still reported as rejected and a dead daemon still reads as
    # a daemon problem — a cached image must not launder either.
    if not force and image_exists(tag):
        return StockItem(image=tag, kind=artifact.kind, title=name,
                         source_path=str(path), dispense_key=key, warm=True,
                         owns_prefix=artifact.kind in NODE_BUILD_KINDS,
                         container_port=CONTAINER_PORTS.get(
                             artifact.kind, DEFAULT_CONTAINER_PORT))

    if artifact.kind in NATIVE_DOCKERFILE_KINDS:
        dockerfile = path / "Dockerfile"
        if not dockerfile.exists():
            raise VendingError(
                f"{artifact.kind} at {path} has no Dockerfile; code-engine "
                "normally generates one, so its absence is the real problem")
        # The engine wrote its own image definition. Building it as-is keeps
        # the artifact's self-description authoritative.
        build(path, tag, dockerfile=str(dockerfile))
        return StockItem(image=tag, kind=artifact.kind, title=name,
                         source_path=str(path), dispense_key=key,
                         container_port=CONTAINER_PORTS.get(artifact.kind,
                                                            DEFAULT_CONTAINER_PORT))

    if artifact.kind in NODE_BUILD_KINDS:
        if not (path / "package.json").exists():
            raise VendingError(
                f"{artifact.kind} at {path} has no package.json; design-engine "
                "normally writes one, so its absence is the real problem")
        # The Dockerfile is written beside the source rather than into it: a
        # generated site is a record of what was generated, and packaging it
        # must not edit that record.
        with tempfile.TemporaryDirectory() as tmp:
            df = Path(tmp) / "Dockerfile"
            df.write_text(NEXT_DOCKERFILE.replace("__REBASE__", _NEXT_REBASE),
                          encoding="utf-8")
            build(path, tag, dockerfile=str(df),
                  build_args={"NEXT_BASE_PATH": f"/dispensed/{key}"})
        return StockItem(image=tag, kind=artifact.kind, title=name,
                         source_path=str(path), dispense_key=key,
                         owns_prefix=True,
                         container_port=CONTAINER_PORTS.get(artifact.kind,
                                                            DEFAULT_CONTAINER_PORT))

    page = _static_page(artifact, provenance)
    with tempfile.TemporaryDirectory() as tmp:
        ctx = Path(tmp)
        (ctx / "index.html").write_text(page, encoding="utf-8")
        (ctx / "Dockerfile").write_text(
            "FROM nginx:alpine\n"
            "COPY index.html /usr/share/nginx/html/index.html\n",
            encoding="utf-8")
        build(ctx, tag)
    return StockItem(image=tag, kind=artifact.kind, title=name,
                     source_path=str(path), dispense_key=key)


def vend(item: StockItem, container_port: int | None = None) -> DispensedCopy:
    """Hand out a fresh disposable copy of already-built stock.

    The port comes from the item unless a caller overrides it, so a product
    is reached on the port it actually serves rather than the one that
    happened to be the default.
    """
    return dispense(item.image,
                    container_port=container_port or item.container_port)
