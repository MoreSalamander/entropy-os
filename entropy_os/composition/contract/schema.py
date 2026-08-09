"""The Universal Engine Contract — the shapes every engine speaks.

This module is the keystone of the whole architecture. An "engine" here is
anything — a leaf wrapping one specialized system, or a composite wrapping
many — that can describe itself, execute capabilities, report health/state,
and narrate what happened as semantic events. Because composites speak the
same contract they consume, composition is recursive by construction:

    ENGINE  →  can join a  →  SYSTEM  →  which is itself an  →  ENGINE

Nothing in this file knows about Research, Software, University, or Web.
Nothing in this file knows about Temporal or DataHub. That ignorance is the
point: the contract is the abstraction boundary that lets a higher-order
system consume a composed system without knowing what is inside it.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

# 1.1 adds ExecuteResult.verdicts. Additive and optional, so a 1.0 consumer
# reading a 1.1 result is unaffected and a 1.1 consumer reading a 1.0 result
# sees an empty list — which it must not read as "nothing was checked".
CONTRACT_VERSION = "1.1"


def now_iso() -> str:
    """UTC timestamps everywhere; provenance is worthless without a clock."""
    return datetime.now(UTC).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


# --------------------------------------------------------------------------- #
# Identity — "what are you, and what composes you?"
# --------------------------------------------------------------------------- #

class CompositionNode(BaseModel):
    """One node of the composition tree, nested recursively.

    A leaf's tree is just itself. A composite's tree carries its members'
    trees, so a single GET /identity on the top system answers the question
    "what systems compose you?" all the way down — self-description is a
    contract feature, not documentation.
    """
    name: str
    kind: Literal["leaf", "composite"]
    summary: str = ""
    members: list[CompositionNode] = Field(default_factory=list)


class EngineIdentity(BaseModel):
    name: str                       # stable machine name, e.g. "research-engine"
    version: str = "0.1.0"
    description: str = ""
    kind: Literal["leaf", "composite"] = "leaf"
    # DataHub platform this engine emits its OWN provenance under. Federation
    # references these URNs; it never re-emits an engine's internal graph.
    datahub_platform: str = ""
    composition: CompositionNode | None = None


# --------------------------------------------------------------------------- #
# Capabilities — "what can you do?"
# --------------------------------------------------------------------------- #

class FieldSpec(BaseModel):
    """One input/output field. Deliberately simpler than full JSON Schema:
    enough for discovery, routing, and UI rendering without dragging a schema
    library across every engine boundary."""
    type: Literal["string", "number", "boolean", "object", "array"] = "string"
    description: str = ""
    required: bool = False


class CapabilitySpec(BaseModel):
    name: str                       # dotted, e.g. "research.investigate"
    summary: str = ""
    # The engine name that ultimately serves this capability. For a composite
    # this is the composite itself — callers must NOT need to know members.
    # The true path of execution is visible in Provenance, not here.
    engine: str = ""
    kind: Literal["atomic", "composed"] = "atomic"
    long_running: bool = False      # hint for callers to use generous timeouts
    inputs: dict[str, FieldSpec] = Field(default_factory=dict)
    outputs: dict[str, FieldSpec] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)


class EngineManifest(BaseModel):
    contract_version: str = CONTRACT_VERSION
    identity: EngineIdentity
    capabilities: list[CapabilitySpec] = Field(default_factory=list)
    events_emitted: list[str] = Field(default_factory=list)
    workflows: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Execution — "do this," with provenance threaded through every level
# --------------------------------------------------------------------------- #

class ExecutionRef(BaseModel):
    """Identity of one execution, threading recursion levels together.

    objective_id names the top-level human objective; parent_execution_id
    chains composite → member calls, so provenance survives arbitrary
    nesting depth without any level knowing how deep it sits.
    """
    execution_id: str = Field(default_factory=lambda: new_id("exec"))
    objective_id: str = ""
    workflow_id: str = ""           # set when a durable workflow owns this run
    parent_execution_id: str = ""


class ExecuteRequest(BaseModel):
    capability: str
    inputs: dict = Field(default_factory=dict)
    ref: ExecutionRef = Field(default_factory=ExecutionRef)
    timeout_s: float = 3600.0       # engines do real work; default to patience


class ArtifactRef(BaseModel):
    kind: str                       # "report" | "project" | "site" | "lesson" | ...
    path: str = ""                  # local path or URL — where the artifact lives
    description: str = ""


class SemanticEvent(BaseModel):
    """A past-tense fact about a meaningful change in system state.

    Events DESCRIBE what happened ("ResearchCompleted", "CurriculumCreated").
    They never instruct another engine how to respond — that restraint is
    what keeps the engines autonomous.
    """
    event_id: str = Field(default_factory=lambda: new_id("evt"))
    ts: str = Field(default_factory=now_iso)
    kind: str                       # e.g. "ResearchCompleted"
    engine: str = ""                # who observed/produced the fact
    subject: str = ""               # what changed: a DataHub URN or stable slug
    objective_id: str = ""
    payload: dict = Field(default_factory=dict)


class Provenance(BaseModel):
    """Where a result came from — carried up through every composition level."""
    engine: str = ""
    capability: str = ""
    ref: ExecutionRef = Field(default_factory=ExecutionRef)
    started_at: str = ""
    finished_at: str = ""
    # Datasets this execution created/updated in the engine's OWN platform.
    # These URNs are the anchor points the DataHub federation stitches across.
    datahub_urns: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    # For composites: the member provenances beneath this one. A consumer may
    # ignore this entirely (opacity) or descend it (transparency) — both are
    # legitimate, which is exactly the abstraction the contract promises.
    children: list[Provenance] = Field(default_factory=list)


class ArtifactNotServed(Exception):
    """No engine will serve that file.

    Deliberately one error for every reason — outside the root, not a file,
    gone, or simply not this engine's — because distinguishing them to the
    caller would turn a read surface into a probe for what exists on the
    host's disk.
    """


class Determinism(StrEnum):
    """How a verdict was reached — the honest label, not the flattering one."""

    HARD = "hard"      # a recorded fact: a test result, a count, a score
    SOFT = "soft"      # an opinion (a judge model). Recorded, never proof.
    HUMAN = "human"    # a person decided. The proper verifier for judgment calls.


class Verdict(BaseModel):
    """One check an engine ran on its own work, reported at full fidelity.

    Engines have always verified themselves — ruff and pytest on generated
    code, a render gate on a generated site, an answerability gate on a
    lesson. What they could not do was SAY so across the contract: results
    collapsed into a single boolean at the adapter, and a consumer holding
    `verified: true` had no way to re-check the claim or to see that half of
    it came from a judge model rather than a test run.

    That collapse is the thing the doctrine forbids. A verdict carries
    evidence, never a bare boolean, and it declares its determinism honestly
    so a consumer can present a judge's opinion as an opinion. Composition-
    level gate verdicts extend this same shape (see scaffold/verdict.py):
    one vocabulary, whether the check ran inside an engine or between two.
    """

    gate: str
    determinism: Determinism
    passed: bool
    evidence: str                              # what was checked, what was found
    facts: dict = Field(default_factory=dict)  # the values the call was made on


class ExecuteResult(BaseModel):
    status: Literal["completed", "failed"]
    outputs: dict = Field(default_factory=dict)
    artifacts: list[ArtifactRef] = Field(default_factory=list)
    events: list[SemanticEvent] = Field(default_factory=list)
    provenance: Provenance = Field(default_factory=Provenance)
    # What the engine checked about its own output. Empty means the engine
    # reported nothing — NOT that nothing was checked and never that
    # everything passed. A consumer that renders acceptance without these is
    # showing a conclusion while withholding the reasoning.
    verdicts: list[Verdict] = Field(default_factory=list)
    error: str = ""


# --------------------------------------------------------------------------- #
# Observability — "how are you, what are you doing, what do you know?"
# --------------------------------------------------------------------------- #

# The output fields that IDENTIFY what an execution produced — the handles by
# which later work can find, reference, or update it.
#
# This lives in the contract, not in any consumer, because it is a statement
# about ExecuteResult.outputs rather than about what any one consumer does
# with it. Federation publishes these as queryable dataset properties, impact
# analysis reads them as the record of what exists, and a composition gate
# checks that a stage produced any of them — three consumers, one convention,
# and none of them a dependency of the others.
#
# Keeping it here also keeps this module a dependency-free leaf, which matters
# concretely: composition gates are evaluated inside the Temporal workflow
# sandbox, so anything they import must be free of I/O. An earlier version
# imported this from the federation package and dragged httpx (and therefore
# urllib) into the sandbox, which Temporal correctly refused.
IDENTIFYING_OUTPUTS = ("session_id", "project_id", "product_name",
                       "learning_order", "subject", "out_dir")


def identifying(outputs: dict) -> dict:
    """The identifying subset of an execution's outputs."""
    return {k: v for k, v in outputs.items() if k in IDENTIFYING_OUTPUTS}


class HealthReport(BaseModel):
    engine: str = ""
    status: Literal["ok", "degraded", "down"] = "ok"
    checks: dict[str, str] = Field(default_factory=dict)
    ts: str = Field(default_factory=now_iso)


class StateSnapshot(BaseModel):
    """What the engine is DOING — execution counters, never knowledge."""
    engine: str = ""
    active_executions: list[str] = Field(default_factory=list)
    executions_total: int = 0
    events_total: int = 0
    last_event_ts: str = ""
    counters: dict[str, int] = Field(default_factory=dict)


class ContextDescriptor(BaseModel):
    """What situation the engine is operating in — recent sessions/projects.
    Descriptive pointers, not a dump of the engine's Context Graph."""
    engine: str = ""
    description: str = ""
    recent: list[dict] = Field(default_factory=list)
    stats: dict[str, int] = Field(default_factory=dict)


class KnowledgeDescriptor(BaseModel):
    """What the engine KNOWS — pointers to its knowledge stores and its
    DataHub platform, not the knowledge itself. The graphs stay domain-owned;
    the contract only makes them discoverable."""
    engine: str = ""
    description: str = ""
    datahub_platform: str = ""
    stores: list[dict] = Field(default_factory=list)
    stats: dict[str, int] = Field(default_factory=dict)
