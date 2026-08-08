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
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

from ..contract import ArtifactRef
from ..scaffold import StageJudgment
from .docker import DispensedCopy, VendingError, available, build, dispense

# Artifact kinds this machine can package, and how.
STATIC_KINDS = ("report", "lesson")
NATIVE_DOCKERFILE_KINDS = ("project",)
UNSUPPORTED_KINDS = {
    "site": "a generated Next.js site is source, not a served bundle; "
            "packaging it needs a node build stage this machine does not "
            "have yet",
    "sidecar": "a sidecar is a model of another artifact, not a product",
}


@dataclass(frozen=True)
class StockItem:
    """One packaged, dispensable product."""
    image: str
    kind: str
    title: str
    source_path: str


def image_tag(objective_id: str, kind: str, name: str) -> str:
    """A readable tag beats a hash for anyone reading `docker images`."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40] or "item"
    return f"one-engine/{kind}-{slug}:{objective_id}"


def packageable(artifact: ArtifactRef) -> tuple[bool, str]:
    """Whether this kind can be packaged, and why not when it cannot."""
    if artifact.kind in UNSUPPORTED_KINDS:
        return False, UNSUPPORTED_KINDS[artifact.kind]
    if artifact.kind not in STATIC_KINDS + NATIVE_DOCKERFILE_KINDS:
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
            judgment: StageJudgment | None = None) -> StockItem:
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
    provenance = f"{artifact.kind} from objective {objective_id}"

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
                         source_path=str(path))

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
                     source_path=str(path))


def vend(item: StockItem, container_port: int = 80) -> DispensedCopy:
    """Hand out a fresh disposable copy of already-built stock."""
    return dispense(item.image, container_port=container_port)
