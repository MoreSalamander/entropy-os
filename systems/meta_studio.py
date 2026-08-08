"""System B — the recursion proof.

meta-studio is a second-level composite whose ONLY member is the unified
one-engine system, consumed through the Universal Engine Contract at a URL.
It is built from the same CompositeEngine class, holds its member with the
same RemoteEngine class, and serves the same contract through the same app
factory. Nothing in this file knows that its member contains four engines.

That is the whole claim, stated as code rather than as a diagram:

    research + software + university + web
        → one-engine          (a composite, exposing the contract)
        → a capability        (consumed by URL, opaquely)
        → meta-studio         (a composite of that capability)
        → …                   (the same move, available again)

meta-studio declares its own pipeline, `studio.launch_venture`, whose first
stage delegates an ENTIRE four-engine composition to its member as a single
capability call — and then adds a stage of its own on top.

Run it:  python -m systems.meta_studio
"""

from __future__ import annotations

import uvicorn

from one_engine.composite import CompositeEngine
from one_engine.config import REPO_ROOT, load_config
from one_engine.contract import FieldSpec
from one_engine.contract.http import build_engine_app
from one_engine.events.bus import EventBus
from one_engine.federation.datahub import FederationBridge
from one_engine.orchestration.stages import Acc, ComposedPipeline, PlannedStage, Registry
from one_engine.remote import RemoteEngine


def _unified_inputs(inputs: dict, acc: Acc) -> dict:
    """Delegate the whole four-engine composition as ONE capability call.

    meta-studio passes a topic and gets back a researched, taught, built, and
    published platform. It does not know — and this function could not
    exercise even if it wanted to — that four autonomous engines, a DataHub
    federation, and a Temporal workflow produced that result."""
    return {"topic": inputs["topic"],
            "audience": inputs.get("audience",
                                   "adult beginners learning by building")}


def _launch_site_inputs(inputs: dict, acc: Acc) -> dict:
    """A stage meta-studio adds on top of its member's whole composition:
    a venture-facing launch page for what the unified system produced."""
    topic = inputs["topic"]
    stages = acc.get("unified", {}).get("stages") or []
    product = ""
    for s in stages:
        product = product or (s.get("outputs") or {}).get("product_name", "")
    product = product or f"{topic} Academy"
    return {"request": (
        f"A venture launch page for '{product}'. It should position the "
        f"product for early adopters and investors: what it teaches "
        f"({topic}), who it is for, and why a system that researches, "
        f"teaches, builds, and ships end to end is different. Confident, "
        f"minimal, credible.")}


LAUNCH_VENTURE = ComposedPipeline(
    name="studio.launch_venture",
    summary="Take a technology to market: commission an entire learning "
            "platform from the unified intelligence system, then produce a "
            "venture launch presence for it.",
    inputs={"topic": FieldSpec(type="string", required=True),
            "audience": FieldSpec(type="string")},
    tags=["composed", "second-level"],
    stages=[
        # Stage 1 is a FOUR-ENGINE COMPOSITION, called as one capability.
        PlannedStage(1, "unified", "compose.learning_platform",
                     _unified_inputs, timeout_s=14400.0),
        # Stage 2 is meta-studio's own work, on top of that result.
        PlannedStage(2, "unified", "web.generate_site", _launch_site_inputs),
    ])

STUDIO_PIPELINES: Registry = {LAUNCH_VENTURE.name: LAUNCH_VENTURE}


def build_meta_studio() -> CompositeEngine:
    cfg = load_config()
    # ONE member, addressed by URL. This is the entire integration surface
    # between the second level and the first.
    members = {"unified": RemoteEngine(cfg.unified_url)}
    bus = EventBus(REPO_ROOT / "storage_data" / "meta_studio_events.jsonl")
    federation = FederationBridge(cfg.datahub_gms, platform="meta-studio",
                                  env=cfg.datahub_env)
    return CompositeEngine(
        name=cfg.system_b_name, members=members, bus=bus,
        federation=federation, datahub_platform="meta-studio",
        pipelines=STUDIO_PIPELINES,
        description=("A studio that takes technologies to market. Composed "
                     "of one capability: an intelligence system that can "
                     "research, teach, build, and publish."))


def build_app():
    studio = build_meta_studio()
    return build_engine_app(studio, title="meta-studio · contract")


app = build_app()


if __name__ == "__main__":
    cfg = load_config()
    uvicorn.run(app, host="127.0.0.1", port=cfg.system_b_port,
                log_level="warning")
