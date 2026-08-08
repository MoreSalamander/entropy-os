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
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

CONTRACT_VERSION = "1.0"


def now_iso() -> str:
    """UTC timestamps everywhere; provenance is worthless without a clock."""
    return datetime.now(timezone.utc).isoformat()


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
    members: list["CompositionNode"] = Field(default_factory=list)


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
    children: list["Provenance"] = Field(default_factory=list)


class ExecuteResult(BaseModel):
    status: Literal["completed", "failed"]
    outputs: dict = Field(default_factory=dict)
    artifacts: list[ArtifactRef] = Field(default_factory=list)
    events: list[SemanticEvent] = Field(default_factory=list)
    provenance: Provenance = Field(default_factory=Provenance)
    error: str = ""


# --------------------------------------------------------------------------- #
# Observability — "how are you, what are you doing, what do you know?"
# --------------------------------------------------------------------------- #

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
