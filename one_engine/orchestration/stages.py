"""Composed pipelines — pure declarations, no effects.

A ComposedPipeline is how a composite says "I offer this capability, and here
is the sequence of member capabilities that produces it." Pipelines are
DECLARED PER COMPOSITE, never global: a second-level system consumes its
member's composed capabilities as ordinary capabilities, and must not mistake
them for pipelines it can run itself. That distinction is what keeps
recursion sound at depth greater than one.

This module is deliberately import-light (no HTTP, no bus, no federation) so
the Temporal workflow sandbox can import pipeline SHAPE safely. The effectful
half lives in runtime.py.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Callable

from pydantic import BaseModel

from ..contract import CapabilitySpec, ExecuteResult, FieldSpec

# Accumulated outputs: member key ("research", "university", …) → outputs.
Acc = dict[str, dict]


class StageOutcome(BaseModel):
    """What one stage activity returns to the workflow: the contract result
    plus the federation URN that stage published (empty when DataHub is
    down). A model rather than a tuple so Temporal's converter round-trips
    it with its types intact across replay."""
    result: ExecuteResult
    stage_urn: str = ""


@dataclass(frozen=True)
class PlannedStage:
    seq: int
    engine: str            # member key in the composite's members mapping
    capability: str
    make_inputs: Callable[[dict, Acc], dict]   # (objective inputs, acc) → inputs
    timeout_s: float = 3600.0


@dataclass(frozen=True)
class ComposedPipeline:
    name: str
    summary: str
    stages: list[PlannedStage]
    inputs: dict[str, FieldSpec] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)

    def spec(self, engine_name: str) -> CapabilitySpec:
        return CapabilitySpec(
            name=self.name, summary=self.summary, engine=engine_name,
            kind="composed", long_running=True, inputs=dict(self.inputs),
            outputs={"objective_id": FieldSpec(),
                     "stages": FieldSpec(type="array"),
                     "objective_urn": FieldSpec(
                         description="DataHub dataset for the composed run")},
            tags=list(self.tags))

    def stage_by_seq(self, seq: int) -> PlannedStage:
        for stage in self.stages:
            if stage.seq == seq:
                return stage
        raise KeyError(f"no stage {seq} in pipeline {self.name!r}")


Registry = dict[str, ComposedPipeline]


# --------------------------------------------------------------------------- #
# The unified system's flagship pipeline.
#
# Stage input builders receive the accumulated outputs of prior stages — this
# is where cross-domain information actually flows: research's discoveries
# shape the curriculum, the curriculum's learning order shapes the software
# request, the software's product shapes the web experience.
# --------------------------------------------------------------------------- #

def _research_inputs(inputs: dict, acc: Acc) -> dict:
    return {"topic": inputs["topic"]}


def _university_inputs(inputs: dict, acc: Acc) -> dict:
    topic = inputs["topic"]
    return {"goal": f"Understand {topic}: the core concepts, how it works, "
                    f"and how to build with it in practice",
            "learner_name": inputs.get("learner_name", "one-engine")}


def _software_inputs(inputs: dict, acc: Acc) -> dict:
    topic = inputs["topic"]
    order = (acc.get("university", {}).get("learning_order") or [])[:6]
    concepts = ", ".join(order) if order else topic
    audience = inputs.get("audience", "adult beginners learning by building")
    return {"request": (
        f"An educational web platform that teaches {topic}. "
        f"The curriculum covers, in order: {concepts}. "
        f"It needs lesson content pages, quizzes with graded answers, and "
        f"learner progress tracking with mastery levels per concept. "
        f"Audience: {audience}.")}


def _web_inputs(inputs: dict, acc: Acc) -> dict:
    topic = inputs["topic"]
    product = acc.get("software", {}).get("product_name") or f"{topic} Academy"
    order = (acc.get("university", {}).get("learning_order") or [])[:4]
    return {"request": (
        f"A public website for '{product}', an educational platform that "
        f"teaches {topic}. It should present the curriculum "
        f"({', '.join(order) if order else topic}), explain the "
        f"learn-by-building method, and invite learners to enroll.")}


LEARNING_PLATFORM = ComposedPipeline(
    name="compose.learning_platform",
    summary="Research a technology and turn what is discovered into an "
            "educational software platform with a public web experience — "
            "research → curriculum → software → web.",
    inputs={"topic": FieldSpec(type="string", required=True,
                               description="the technology to learn/teach"),
            "audience": FieldSpec(type="string"),
            "approve_before_stage": FieldSpec(
                type="number",
                description="pause for human approval before this stage "
                            "(requires the Temporal orchestrator)")},
    tags=["composed", "flagship"],
    stages=[
        PlannedStage(1, "research", "research.investigate", _research_inputs),
        PlannedStage(2, "university", "university.design_curriculum",
                     _university_inputs),
        PlannedStage(3, "software", "software.build", _software_inputs),
        PlannedStage(4, "web", "web.generate_site", _web_inputs),
    ])

# The unified system's registry. A composite is constructed with a registry;
# this one is the default because it is what one-engine itself offers.
COMPOSED_PIPELINES: Registry = {LEARNING_PLATFORM.name: LEARNING_PLATFORM}


def concept_representations(topic: str, acc: Acc) -> dict[str, str]:
    """Identity resolution, with receipts: how each domain locally represents
    the objective's shared subject. Only domains that actually produced an
    identifier appear — no manufactured links."""
    reps: dict[str, str] = {"name": topic}
    if sid := acc.get("research", {}).get("session_id"):
        reps["research_session"] = sid
    if sid := acc.get("university", {}).get("session_id"):
        reps["curriculum_session"] = sid
    if order := acc.get("university", {}).get("learning_order"):
        reps["curriculum_concepts"] = ", ".join(order[:8])
    if pid := acc.get("software", {}).get("project_id"):
        reps["software_project"] = pid
    if name := acc.get("software", {}).get("product_name"):
        reps["software_product"] = name
    if pid := acc.get("web", {}).get("project_id"):
        reps["web_project"] = pid
    # Second-level composition: when a member IS a composed system, its
    # objective URN is that domain's representation of the same subject.
    if urn := acc.get("unified", {}).get("objective_urn"):
        reps["unified_objective"] = urn
    return reps


def new_objective_id() -> str:
    return f"obj-{uuid.uuid4().hex[:12]}"
