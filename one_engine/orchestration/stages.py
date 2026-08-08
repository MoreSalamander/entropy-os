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
from collections.abc import Callable
from dataclasses import dataclass, field

from pydantic import BaseModel

from ..contract import CapabilitySpec, ExecuteResult, FieldSpec
from ..scaffold import CompositionGate, StageJudgment, gates_for

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
    # Deterministic predicate over data the orchestrator already holds. It is
    # evaluated INSIDE the workflow, so it must never do I/O — everything it
    # needs (including impact analysis) arrives in `acc` beforehand.
    skip_if: Callable[[dict, Acc], bool] | None = None
    skip_reason: str = ""
    # Deliberate override of the capability's usual gates. Left empty — the
    # normal case — the stage is judged by whatever the scaffold's policy says
    # judges this capability, so a stage and a direct call face the same bar.
    gates: tuple[CompositionGate, ...] | None = None

    def should_skip(self, inputs: dict, acc: Acc) -> bool:
        return bool(self.skip_if and self.skip_if(inputs, acc))

    def resolved_gates(self) -> tuple[CompositionGate, ...]:
        return gates_for(self.capability) if self.gates is None else self.gates

    def judge(self, result: ExecuteResult) -> StageJudgment:
        """Run every gate that judges this capability against the result."""
        return StageJudgment(
            stage_seq=self.seq, engine=self.engine,
            verdicts=[g.evaluate(result, self.seq, self.engine)
                      for g in self.resolved_gates()])


@dataclass(frozen=True)
class ComposedPipeline:
    name: str
    summary: str
    stages: list[PlannedStage]
    inputs: dict[str, FieldSpec] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    # Optional context gathered once, before any stage runs, and seeded into
    # `acc` under PREPARED_KEY. This is where an evolving pipeline learns what
    # its subject already affects. Named rather than inlined because it does
    # I/O and therefore has to run in an activity.
    prepare: str = ""

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

# Where a pipeline's prepared context lands in `acc`. Underscore-prefixed so
# it can never collide with a member key.
PREPARED_KEY = "_prepared"


# --------------------------------------------------------------------------- #
# The unified system's flagship pipeline.
#
# Stage input builders receive the accumulated outputs of prior stages — this
# is where cross-domain information actually flows: research's discoveries
# shape the curriculum, the curriculum's learning order shapes the software
# request, the software's product shapes the web experience.
# --------------------------------------------------------------------------- #

# Stage budgets, sized from watching these engines actually run on local
# hardware rather than from a round number. Research is the long pole: it
# extracts evidence with an LLM call per document across a hundred-plus
# sources, then runs six reasoning agents over the resulting graph. A budget
# that expires mid-stage is worse than no budget, because the retry starts
# from zero — so these are generous on purpose, and the orchestrator's job is
# to survive the wait, not to shorten it.
RESEARCH_BUDGET_S = 10800.0     # 3h — acquisition + per-document extraction + 6 agents
CURRICULUM_BUDGET_S = 5400.0    # 1.5h — roadmap synthesis + concept research
BUILD_BUDGET_S = 7200.0         # 2h — research, architecture, generation, verification
SITE_BUDGET_S = 7200.0          # 2h — site research, synthesis, per-page copy, review


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
        PlannedStage(1, "research", "research.investigate", _research_inputs,
                     timeout_s=RESEARCH_BUDGET_S),
        PlannedStage(2, "university", "university.design_curriculum",
                     _university_inputs, timeout_s=CURRICULUM_BUDGET_S),
        PlannedStage(3, "software", "software.build", _software_inputs,
                     timeout_s=BUILD_BUDGET_S),
        PlannedStage(4, "web", "web.generate_site", _web_inputs,
                     timeout_s=SITE_BUDGET_S),
    ])

# --------------------------------------------------------------------------- #
# Evolution: the system does not only generate once — it reacts to new
# information about something it has already built.
#
# The hard part is not re-running; it is knowing what NEEDS re-running. An
# impact report (gathered by the `impact` prepare hook, from the system's own
# event history) seeds `acc`, and each downstream stage skips itself when
# nothing it owns is affected. New research always runs; a curriculum is only
# redesigned if one exists; software is only rebuilt if there is software.
# --------------------------------------------------------------------------- #

def _impact(acc: Acc) -> dict:
    return (acc.get(PREPARED_KEY) or {}).get("impact") or {}


def _affected(acc: Acc, engine: str) -> dict:
    return (_impact(acc).get("affected") or {}).get(engine) or {}


def _evolve_research_inputs(inputs: dict, acc: Acc) -> dict:
    return {"topic": f"What has recently changed about {inputs['topic']}: "
                     f"new releases, deprecations, and current best practice"}


def _evolve_curriculum_inputs(inputs: dict, acc: Acc) -> dict:
    topic = inputs["topic"]
    prior = _affected(acc, "university").get("learning_order") or []
    known = f" The previous curriculum covered: {', '.join(prior[:8])}." if prior else ""
    return {"goal": f"Understand {topic} as it stands today, including what "
                    f"recently changed and why.{known}",
            "learner_name": inputs.get("learner_name", "one-engine")}


def _evolve_software_inputs(inputs: dict, acc: Acc) -> dict:
    topic = inputs["topic"]
    prior = _affected(acc, "software")
    order = (acc.get("university", {}).get("learning_order") or [])[:6]
    product = prior.get("product_name") or f"{topic} Academy"
    return {"request": (
        f"An updated release of '{product}', an educational platform teaching "
        f"{topic}. The curriculum has been revised to: "
        f"{', '.join(order) if order else topic}. Keep lesson pages, graded "
        f"quizzes, and per-concept mastery tracking; reflect what recently "
        f"changed about {topic}.")}


def _evolve_web_inputs(inputs: dict, acc: Acc) -> dict:
    topic = inputs["topic"]
    product = (acc.get("software", {}).get("product_name")
               or _affected(acc, "software").get("product_name")
               or f"{topic} Academy")
    return {"request": (
        f"An updated public website for '{product}', teaching {topic}. "
        f"Lead with what has changed recently in {topic} and why the "
        f"curriculum was revised.")}


EVOLVE_PLATFORM = ComposedPipeline(
    name="compose.evolve",
    summary="React to new information about a subject the system has already "
            "worked on: research what changed, determine impact from the "
            "system's own history, and update only what is actually affected.",
    inputs={"topic": FieldSpec(type="string", required=True,
                               description="the subject to re-evaluate"),
            "approve_before_stage": FieldSpec(type="number")},
    tags=["composed", "evolution"],
    prepare="impact",
    stages=[
        # Perception always runs: you cannot know what changed without looking.
        PlannedStage(1, "research", "research.investigate",
                     _evolve_research_inputs, timeout_s=RESEARCH_BUDGET_S),
        PlannedStage(2, "university", "university.design_curriculum",
                     _evolve_curriculum_inputs,
                     timeout_s=CURRICULUM_BUDGET_S,
                     skip_if=lambda i, acc: not _affected(acc, "university"),
                     skip_reason="no existing curriculum for this subject"),
        PlannedStage(3, "software", "software.build",
                     _evolve_software_inputs, timeout_s=BUILD_BUDGET_S,
                     skip_if=lambda i, acc: not _affected(acc, "software"),
                     skip_reason="no existing software for this subject"),
        PlannedStage(4, "web", "web.generate_site", _evolve_web_inputs,
                     timeout_s=SITE_BUDGET_S,
                     skip_if=lambda i, acc: not _affected(acc, "web"),
                     skip_reason="no existing web experience for this subject"),
    ])


# The unified system's registry. A composite is constructed with a registry;
# this one is the default because it is what one-engine itself offers.
COMPOSED_PIPELINES: Registry = {LEARNING_PLATFORM.name: LEARNING_PLATFORM,
                                EVOLVE_PLATFORM.name: EVOLVE_PLATFORM}


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
