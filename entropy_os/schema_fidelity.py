"""Did the generated code actually use the schema it was given?

Handing a generator real field names and hoping is not metadata-aware
generation, it is metadata-adjacent generation. The difference is invisible
in a demo and obvious in a diff: the catalog said `accepted`,
`accepted_because`, `created_by`, `confidence`, and the first grounded run
produced `hunter_run_id`, `gate_outcome`, `opportunity_type`. It read the
schema, was told to use it, and did not.

So the claim gets a gate rather than a caption. This reads the fields out of
the generated source with `ast` — not a regex over text, because the question
is what the code DECLARES and only a parser knows that — and compares them to
the fields the catalog supplied. The result is a HARD verdict: a recorded
fact about two lists of names, re-checkable by anyone.

A failure here is a result, not an embarrassment. It says the generator
ignored the catalog on this run, which is worth knowing and is exactly the
kind of thing that goes unnoticed when the only evidence is that the code
compiles.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

from .composition.contract import Determinism, Verdict

# Fields every generated model carries regardless of the catalog — counting
# them as fidelity would let a generator score by writing an `id` column.
BOILERPLATE = {"id", "created_at", "updated_at", "deleted_at"}

# Half. A service modelling a subset of a catalog dataset is legitimate — it
# may not need every column — but one that shares fewer than half its field
# names is describing something else and calling it the same thing.
COVERAGE_FLOOR = 0.5


@dataclass(frozen=True)
class Fidelity:
    catalog_fields: set[str]
    generated_fields: set[str]
    matched: set[str]
    files_read: int

    @property
    def coverage(self) -> float:
        usable = self.catalog_fields - BOILERPLATE
        return len(self.matched) / len(usable) if usable else 0.0

    @property
    def missed(self) -> set[str]:
        return (self.catalog_fields - BOILERPLATE) - self.matched


def declared_fields(source: str) -> set[str]:
    """Every field name a module's classes declare.

    Covers both shapes the generator emits: pydantic/dataclass annotations
    (`accepted: bool`) and SQLAlchemy assignments (`accepted = Column(...)`).
    Parsed rather than matched, so a field name appearing in a docstring or a
    comment cannot be mistaken for a declaration.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()
    found: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        for stmt in node.body:
            if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                found.add(stmt.target.id)
            elif isinstance(stmt, ast.Assign):
                for t in stmt.targets:
                    if isinstance(t, ast.Name):
                        found.add(t.id)
    return {f for f in found if not f.startswith("_")}


def measure(project_dir: str | Path, catalog_fields: set[str]) -> Fidelity:
    """Compare what the catalog offered against what the project declares."""
    root = Path(project_dir)
    generated: set[str] = set()
    read = 0
    # Only the model layer. A field name appearing in a route handler or a
    # test says nothing about whether the DATA MODEL adopted the schema.
    for name in ("models.py", "schemas.py", "entities.py", "domain.py"):
        for path in root.rglob(name):
            try:
                generated |= declared_fields(path.read_text(encoding="utf-8",
                                                            errors="replace"))
                read += 1
            except OSError:
                continue
    usable = catalog_fields - BOILERPLATE
    return Fidelity(catalog_fields=catalog_fields, generated_fields=generated,
                    matched=usable & generated, files_read=read)


def verdict(fidelity: Fidelity) -> Verdict:
    """The fidelity measurement, as a contract verdict.

    HARD: it is a comparison of two sets of strings read out of files. No
    model is consulted and nothing is judged — which is the whole reason this
    can settle the claim.
    """
    usable = fidelity.catalog_fields - BOILERPLATE
    if not usable:
        return Verdict(
            gate="agent.schema_fidelity", determinism=Determinism.HARD,
            passed=False,
            evidence="the catalog supplied no field names, so nothing could be "
                     "adopted — this build was not schema-grounded",
            catalog_fields=0)
    if not fidelity.files_read:
        return Verdict(
            gate="agent.schema_fidelity", determinism=Determinism.HARD,
            passed=False,
            evidence="no model module was found in the generated project, so "
                     "adoption could not be checked",
            catalog_fields=len(usable))
    pct = round(fidelity.coverage * 100)
    hit = ", ".join(sorted(fidelity.matched)[:6]) or "none"
    missed = ", ".join(sorted(fidelity.missed)[:6]) or "none"
    return Verdict(
        gate="agent.schema_fidelity", determinism=Determinism.HARD,
        passed=fidelity.coverage >= COVERAGE_FLOOR,
        evidence=(f"{len(fidelity.matched)}/{len(usable)} catalog fields "
                  f"adopted ({pct}%) — used: {hit}; ignored: {missed}"),
        adopted=sorted(fidelity.matched), ignored=sorted(fidelity.missed),
        coverage=pct, floor=int(COVERAGE_FLOOR * 100))
