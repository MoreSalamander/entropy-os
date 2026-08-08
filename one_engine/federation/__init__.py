"""DataHub federation: cross-domain identity, relationships, and provenance
over the engines' own graphs — connected, never flattened."""

from . import impact
from .datahub import FederationBridge
from .semantics import (IDENTIFYING_OUTPUTS, PRIMITIVES, identifying,
                        primitive_for, slugify)

__all__ = ["FederationBridge", "IDENTIFYING_OUTPUTS", "PRIMITIVES",
           "identifying", "impact", "primitive_for", "slugify"]
