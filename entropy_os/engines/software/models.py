"""Typed vocabulary of the software model.

The provenance chain is the invariant everything else leans on:

    Requirement --satisfied_by--> Feature --implemented_by--> Component
    Component --materialized_in--> File(s)
    Component --exposes--> ApiEndpoint --touches--> Entity
    Test --verifies--> Feature
    Decision --shapes--> Component

Generation writes this chain as it writes code; verification and impact
analysis traverse it; evolution checks it against observed reality.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, Field


def now_utc() -> datetime:
    return datetime.now(UTC)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def slug(text: str) -> str:
    import re
    s = re.sub(r"[^a-z0-9]+", "_", text.casefold()).strip("_")
    return s[:40] or "item"


# --------------------------------------------------------------------------
# Phase 1 — the software specification
# --------------------------------------------------------------------------

class Priority(str, Enum):
    MUST = "must"
    SHOULD = "should"
    COULD = "could"


class Requirement(BaseModel):
    id: str = Field(default_factory=lambda: new_id("req"))
    kind: str = "functional"          # functional | nonfunctional | data | security | integration
    text: str
    priority: Priority = Priority.MUST


class SoftwareSpec(BaseModel):
    id: str = Field(default_factory=lambda: new_id("spec"))
    raw_request: str
    product_name: str = ""
    purpose: str = ""
    user_types: list[str] = Field(default_factory=list)
    requirements: list[Requirement] = Field(default_factory=list)
    technical_constraints: list[str] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)   # external systems/services
    candidate_approaches: list[str] = Field(default_factory=list)
    # Real field definitions from a metadata catalog, when the caller supplied
    # them. Carried on the spec rather than left in raw_request because the
    # later phases build their prompts from the SPEC — a schema that lives
    # only in the original wording reaches intent and dies there, which is
    # exactly what happened: the catalog said `accepted`, the generator wrote
    # `gate_outcome`, and nothing noticed.
    catalog_schema: str = ""
    created_at: datetime = Field(default_factory=now_utc)

    def by_kind(self, kind: str) -> list[Requirement]:
        return [r for r in self.requirements if r.kind == kind]


# --------------------------------------------------------------------------
# Phase 2 — research evidence
# --------------------------------------------------------------------------

class ResearchEvidence(BaseModel):
    id: str = Field(default_factory=lambda: new_id("ev"))
    agent: str                        # which research worker produced it
    topic: str                        # technology|architecture|opensource|docs|security|ux
    title: str
    url: str
    summary: str = ""
    extra: dict = Field(default_factory=dict)   # stars, version, vuln ids, …


# --------------------------------------------------------------------------
# Phase 5 — architecture
# --------------------------------------------------------------------------

class EntityField(BaseModel):
    name: str
    type: str = "str"                 # str | int | float | bool | datetime | text
    required: bool = True


class EntityModel(BaseModel):
    """A persisted domain entity → one SQLAlchemy model + one table."""
    name: str                         # PascalCase
    fields: list[EntityField]

    @property
    def snake(self) -> str:
        import re
        return re.sub(r"(?<!^)(?=[A-Z])", "_", self.name).lower()


class ApiEndpoint(BaseModel):
    method: str                       # GET | POST | PUT | DELETE
    path: str                         # /items, /items/{id}
    summary: str
    entity: str = ""                  # EntityModel.name it touches ("" = none)
    action: str = "custom"            # list | get | create | update | delete | custom


class Component(BaseModel):
    id: str = Field(default_factory=lambda: new_id("cmp"))
    name: str                         # snake_case service name, e.g. "user_service"
    purpose: str
    kind: str = "service"             # service | router | store | ui | infra
    feature_ids: list[str] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)     # other component names
    entities: list[str] = Field(default_factory=list)       # EntityModel names owned
    endpoints: list[ApiEndpoint] = Field(default_factory=list)


class Feature(BaseModel):
    id: str = Field(default_factory=lambda: new_id("feat"))
    name: str
    description: str
    requirement_ids: list[str] = Field(default_factory=list)


class Decision(BaseModel):
    """ADR-style record; lives in the graph so WHY survives the session."""
    id: str = Field(default_factory=lambda: new_id("adr"))
    title: str
    decision: str
    rationale: str
    component_names: list[str] = Field(default_factory=list)


class Architecture(BaseModel):
    id: str = Field(default_factory=lambda: new_id("arch"))
    spec_id: str = ""
    stack: dict = Field(default_factory=lambda: {
        "language": "python", "framework": "fastapi",
        "orm": "sqlalchemy", "db": "sqlite", "tests": "pytest",
        "lint": "ruff", "frontend": "static-js", "container": "docker"})
    features: list[Feature] = Field(default_factory=list)
    components: list[Component] = Field(default_factory=list)
    entities: list[EntityModel] = Field(default_factory=list)
    decisions: list[Decision] = Field(default_factory=list)
    auth_enabled: bool = False
    validation_notes: list[str] = Field(default_factory=list)  # what the gates fixed


# --------------------------------------------------------------------------
# Phase 9 — verification
# --------------------------------------------------------------------------

class CheckStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    SKIPPED = "skipped"


class CheckResult(BaseModel):
    check: str                        # ruff | pytest | security | performance | review | docs
    status: CheckStatus
    detail: str = ""
    # structured, e.g. {file,test,message,component}
    failures: list[dict] = Field(default_factory=list)


class VerificationReport(BaseModel):
    results: list[CheckResult] = Field(default_factory=list)
    repair_rounds: int = 0
    known_problems: list[str] = Field(default_factory=list)  # honest residue

    @property
    def passed(self) -> bool:
        return all(r.status != CheckStatus.FAIL for r in self.results)

    def result(self, check: str) -> CheckResult | None:
        for r in self.results:
            if r.check == check:
                return r
        return None


# --------------------------------------------------------------------------
# Phase 10 — impact analysis
# --------------------------------------------------------------------------

class ImpactReport(BaseModel):
    target: str                       # component name
    dependent_components: list[str] = Field(default_factory=list)
    affected_apis: list[str] = Field(default_factory=list)
    affected_tests: list[str] = Field(default_factory=list)
    affected_requirements: list[str] = Field(default_factory=list)
    stale_docs: list[str] = Field(default_factory=list)
    affected_files: list[str] = Field(default_factory=list)
    infra_touchpoints: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------
# Phase 11/12 — evolution + cross-project memory
# --------------------------------------------------------------------------

class EvolutionFinding(BaseModel):
    kind: str                         # drift | vuln | stale_dep | doc_drift | test_failure
    severity: str = "warning"         # blocker | warning | note
    message: str
    subject: str = ""                 # component/file/package concerned


class ProjectOutcome(BaseModel):
    project_id: str
    product_name: str
    stack: dict = Field(default_factory=dict)
    components: int = 0
    entities: int = 0
    endpoints: int = 0
    tests_generated: int = 0
    verification_passed: bool = False
    repair_rounds: int = 0
    patterns: list[str] = Field(default_factory=list)   # named patterns applied
    created_at: datetime = Field(default_factory=now_utc)


class GeneratedProject(BaseModel):
    project_id: str
    spec: SoftwareSpec
    architecture: Architecture
    out_dir: str
    files_written: int = 0
    verification: VerificationReport | None = None
