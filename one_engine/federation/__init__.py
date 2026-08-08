"""DataHub federation: cross-domain identity, relationships, and provenance
over the engines' own graphs — connected, never flattened."""

from .datahub import FederationBridge
from .semantics import PRIMITIVES, primitive_for, slugify

__all__ = ["FederationBridge", "PRIMITIVES", "primitive_for", "slugify"]
