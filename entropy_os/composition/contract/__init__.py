"""Universal Engine Contract: schemas (shapes), protocol (behavior), http
(transport). Import from here — the submodule layout is an implementation
detail."""

from .protocol import ComposableEngine
from .schema import (
    CONTRACT_VERSION,
    IDENTIFYING_OUTPUTS,
    ArtifactRef,
    CapabilitySpec,
    CompositionNode,
    ContextDescriptor,
    Determinism,
    EngineIdentity,
    EngineManifest,
    ExecuteRequest,
    ExecuteResult,
    ExecutionRef,
    FieldSpec,
    HealthReport,
    KnowledgeDescriptor,
    Provenance,
    SemanticEvent,
    StateSnapshot,
    Verdict,
    identifying,
    new_id,
    now_iso,
)

__all__ = [
    "IDENTIFYING_OUTPUTS", "identifying",
    "CONTRACT_VERSION", "ComposableEngine", "ArtifactRef", "CapabilitySpec",
    "CompositionNode", "ContextDescriptor", "EngineIdentity", "EngineManifest",
    "ExecuteRequest", "ExecuteResult", "ExecutionRef", "FieldSpec",
    "HealthReport", "KnowledgeDescriptor", "Provenance", "SemanticEvent",
    "StateSnapshot", "Determinism", "Verdict", "new_id", "now_iso",
]
