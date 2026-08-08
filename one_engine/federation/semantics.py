"""Shared semantic primitives — the cross-domain vocabulary.

The four engines keep their domain-specific schemas (research Claims, learn
Concepts, code Requirements, design Traits). The federation does not force
them into one schema; it maps each domain's *facts* onto a small set of
primitives so the composed system can reason about relationships across
domains: a research finding is Evidence, which grounds a Concept, which
becomes an educational objective, which becomes a software Requirement,
which becomes a web Experience.
"""

from __future__ import annotations

import re

# The cross-domain primitives (Phase 4 of the plan). Deliberately few: every
# additional primitive is a tax on every future engine that joins.
PRIMITIVES = [
    "Entity", "Concept", "Evidence", "Claim", "Artifact", "Capability",
    "Requirement", "Decision", "Task", "Workflow", "Event", "Relationship",
]

# Which primitive each engine's semantic events instantiate. This is the
# mapping that lets a federation consumer treat "ResearchCompleted" and
# "MasteryEvidenceRecorded" as the same KIND of thing (Evidence entering the
# system) without either engine knowing about the other.
EVENT_PRIMITIVES: dict[str, str] = {
    "ResearchPhaseAdvanced": "Task",
    "ResearchCompleted": "Evidence",
    "KnowledgeConsolidated": "Claim",
    "CurriculumCreated": "Concept",
    "LessonBuilt": "Artifact",
    "RoadmapMastered": "Claim",
    "MasteryEvidenceRecorded": "Evidence",
    "MisconceptionDetected": "Claim",
    "LearningSessionCompleted": "Evidence",
    "SoftwareBuildProgress": "Task",
    "SoftwareBuilt": "Artifact",
    "SoftwareVerificationFailed": "Claim",
    "SiteGenerationProgress": "Task",
    "SiteGenerated": "Artifact",
    "ObjectiveStarted": "Workflow",
    "StageCompleted": "Task",
    "ObjectiveCompleted": "Workflow",
    "ImpactAnalyzed": "Decision",
    "RelationshipDiscovered": "Relationship",
}


def primitive_for(event_kind: str) -> str:
    return EVENT_PRIMITIVES.get(event_kind, "Event")


# The output fields that IDENTIFY what a stage produced — the handles by
# which a later run can find, reference, or update that work. Stated once and
# used by both the DataHub federation (as queryable dataset properties) and
# impact analysis (as the record of what exists), so a new engine becomes
# legible to both by naming its outputs conventionally rather than by being
# added to a table somewhere.
IDENTIFYING_OUTPUTS = ("session_id", "project_id", "product_name",
                       "learning_order", "subject", "out_dir")


def identifying(outputs: dict) -> dict:
    return {k: v for k, v in outputs.items() if k in IDENTIFYING_OUTPUTS}


def slugify(text: str, max_len: int = 60) -> str:
    """Stable identity slug for a cross-domain concept ("WebGPU compute
    shaders" → "webgpu-compute-shaders"). Identity resolution in the
    federation starts from the objective's own thread of subject-hood, so
    the same slug names the same concept in every domain's provenance."""
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:max_len].rstrip("-") or "unnamed"
