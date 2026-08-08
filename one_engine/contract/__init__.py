"""Universal Engine Contract: schemas (shapes), protocol (behavior), http
(transport). Import from here — the submodule layout is an implementation
detail."""

from .protocol import ComposableEngine
from .schema import (
                     CONTRACT_VERSION,
                     ArtifactRef,
                     CapabilitySpec,
                     CompositionNode,
                     ContextDescriptor,
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
                     new_id,
                     now_iso,
)

__all__ = [
    "CONTRACT_VERSION", "ComposableEngine", "ArtifactRef", "CapabilitySpec",
    "CompositionNode", "ContextDescriptor", "EngineIdentity", "EngineManifest",
    "ExecuteRequest", "ExecuteResult", "ExecutionRef", "FieldSpec",
    "HealthReport", "KnowledgeDescriptor", "Provenance", "SemanticEvent",
    "StateSnapshot", "new_id", "now_iso",
]
