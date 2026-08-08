"""DataHub federation: cross-domain identity, relationships, and provenance
over the engines' own graphs — connected, never flattened."""

from . import impact
from .datahub import FederationBridge
from .semantics import PRIMITIVES, primitive_for, slugify

# IDENTIFYING_OUTPUTS / identifying() deliberately are NOT re-exported here.
# They belong to the contract, and this package imports httpx — a composition
# gate that reached for them through federation would drag the network stack
# into the Temporal workflow sandbox. Import them from one_engine.contract.
__all__ = ["FederationBridge", "PRIMITIVES", "impact", "primitive_for",
           "slugify"]
