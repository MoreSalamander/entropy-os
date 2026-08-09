"""Turn a catalog schema into an entity the architecture must contain.

Asking a model to use the field names it was given is a request, and the
measurement said it was declined: handed seven real columns, the generator
adopted one. Prompting harder is the same request in a louder voice, and it
would still be a request.

So the scaffold decides instead. The catalog block is parsed — deterministic,
no model — into a real EntityModel, and that entity is merged into whatever
the architecture proposed. The model still designs the service: components,
endpoints, relationships, everything else it is good at. It simply does not
get to rename a column that exists in the catalog.

This is the same rule the rest of the system runs on, applied one level down.
An LLM proposes; something that cannot hallucinate decides. The difference
here is only that the thing being decided is a list of names.
"""

from __future__ import annotations

import re

from .models import EntityField, EntityModel

# The brief's shape, written by the reader: "    accepted : boolean".
FIELD_LINE = re.compile(r"^\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*(?::\s*(?P<type>.+))?$")
# A dataset header: "outcome-0 [veritas]" — possibly with a lineage suffix.
HEADER_LINE = re.compile(r"^(?P<name>[^\s\[][^\[]*?)\s*\[(?P<platform>[^\]]+)\]")

# Catalog types are whatever the source system called them; the generated code
# is Python. Anything unrecognised becomes str, which is the safe direction:
# a string column holding a number is inconvenient, the reverse breaks.
TYPE_MAP = {
    "boolean": "bool", "bool": "bool",
    "int": "int", "integer": "int", "long": "int", "bigint": "int",
    "float": "float", "double": "float", "number": "float", "decimal": "float",
    "date": "datetime", "datetime": "datetime", "timestamp": "datetime",
    "text": "text",
}

# Columns the generated model gets on its own. Forcing them in from the
# catalog would collide with the scaffolding every project already has.
SKIP = {"id", "created_at", "updated_at", "deleted_at"}


def _pascal(name: str) -> str:
    parts = re.split(r"[^A-Za-z0-9]+", name)
    return "".join(p[:1].upper() + p[1:] for p in parts if p) or "CatalogRecord"


def parse(catalog_schema: str) -> list[EntityModel]:
    """Every dataset in the brief, as an entity with its real columns."""
    entities: list[EntityModel] = []
    current: str = ""
    fields: list[EntityField] = []

    def flush() -> None:
        if current and fields:
            entities.append(EntityModel(name=_pascal(current), fields=list(fields)))

    for line in (catalog_schema or "").splitlines():
        if not line.strip():
            continue
        header = HEADER_LINE.match(line)
        if header and not line.startswith(" "):
            flush()
            current, fields[:] = header.group("name").strip(), []
            continue
        m = FIELD_LINE.match(line)
        if not m or not current:
            continue
        name = m.group("name")
        if name in SKIP or any(f.name == name for f in fields):
            continue
        raw = (m.group("type") or "").strip().lower()
        fields.append(EntityField(name=name, type=TYPE_MAP.get(raw, "str"),
                                  required=False))
    flush()
    return entities


def merge(proposed: list[EntityModel], catalog: list[EntityModel]) -> list[EntityModel]:
    """Put the catalog's entities into the architecture, authoritatively.

    A proposed entity with the same name is REPLACED rather than merged field
    by field: the catalog is the source of truth about what that record
    contains, and keeping the model's extra invented columns beside the real
    ones is how a schema quietly becomes approximate. Entities the model
    invented for its own purposes are left alone — the catalog says nothing
    about them, so it does not get a vote.
    """
    if not catalog:
        return proposed
    by_name = {e.name.lower(): e for e in catalog}
    out = [e for e in proposed if e.name.lower() not in by_name]
    return catalog + out
