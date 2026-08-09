"""Finding what a run actually produced.

Stages now record their `ArtifactRef`s in the event log, so a path written
today is a path the vending machine can package tomorrow without guessing.
The earliest runs — including the flagship — predate that, and their outputs
were reachable only by knowing each engine's private naming convention.

Rather than pretend those runs said nothing, this module resolves them by
convention and **labels every artifact with how it was obtained**:

    origin="recorded"   the run wrote this path down
    origin="convention" derived from an id the run did record

That distinction is the whole point. A convention-resolved path is a good
guess, not a fact, and anything downstream — a vending machine deciding what
to package, a page telling a visitor where a file came from — deserves to know
which one it is holding.

Storage roots are configurable because the engines' own storage lives beside
each engine on a laptop and somewhere else entirely in a container.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..paths import ENGINE_KEYS, engine_storage

# Engine key -> (env override, default subpath under the engine repo, kind)
# Mirrors what each engine actually does with its own storage; duplicated here
# deliberately, because reading an engine's private layout is exactly the thing
# recorded artifacts exist to stop needing.
# Subpaths are relative to an engine's OWN storage root, which the layout
# module hands out per contract member key. They used to be relative to a
# repository root, back when "where does this engine keep things" and "which
# checkout is it" were the same question.
_CONVENTIONS = {
    "research": ("ONE_ENGINE_ARTIFACTS_RESEARCH", "reports", "report"),
    "software": ("ONE_ENGINE_ARTIFACTS_SOFTWARE", "projects", "project"),
    "web": ("ONE_ENGINE_ARTIFACTS_WEB", "sites", "site"),
    "university": ("ONE_ENGINE_ARTIFACTS_UNIVERSITY", "lessons", "lesson"),
}


@dataclass(frozen=True)
class ResolvedArtifact:
    """One output of one stage, and how confident we are about where it is."""
    kind: str
    path: str
    description: str
    engine: str
    stage_seq: int
    origin: str          # "recorded" | "convention"
    exists: bool
    size_bytes: int
    file_count: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind, "path": self.path,
            "description": self.description, "engine": self.engine,
            "stage_seq": self.stage_seq, "origin": self.origin,
            "exists": self.exists, "size_bytes": self.size_bytes,
            "file_count": self.file_count,
        }


def _root_for(engine: str, roots: dict[str, str]) -> Path | None:
    entry = _CONVENTIONS.get(engine)
    if entry is None:
        return None
    env_key, subpath, _kind = entry
    if override := os.environ.get(env_key):
        return Path(override)
    root = roots.get(engine, "")
    return Path(root) / subpath if root else None


def _measure(path: Path) -> tuple[bool, int, int]:
    """Size and file count, so a caller can show real weight rather than a name."""
    if not path.exists():
        return False, 0, 0
    if path.is_file():
        return True, path.stat().st_size, 1
    total = count = 0
    for f in path.rglob("*"):
        if f.is_file():
            try:
                total += f.stat().st_size
            except OSError:
                continue
            count += 1
    return True, total, count


def _by_convention(engine: str, produced: dict[str, Any],
                   roots: dict[str, str]) -> tuple[str, str] | None:
    """(path, kind) for a stage that recorded ids but not paths."""
    root = _root_for(engine, roots)
    entry = _CONVENTIONS.get(engine)
    if root is None or entry is None:
        return None
    kind = entry[2]

    if engine == "research":
        sid = produced.get("session_id")
        return (str(root / f"{sid}.md"), kind) if sid else None
    if engine == "university":
        sid = produced.get("session_id")
        return (str(root / str(sid)), kind) if sid else None
    # software and web name their output directory by project id
    pid = produced.get("project_id")
    return (str(root / str(pid)), kind) if pid else None


# Where each engine announces its own output ids when the stage record did not
# carry them. The very earliest runs recorded neither artifacts NOR `produced`,
# but they still narrated what they had made — so the ids are recoverable from
# the engines' own completion events.
_FACT_IDS = {
    "research": ("ResearchCompleted", "session_id"),
    "university": ("CurriculumCreated", "session_id"),
    "software": ("SoftwareBuilt", "project_id"),
    "web": ("SiteGenerated", "project_id"),
}


def _ids_from_facts(engine: str, facts: list[dict[str, Any]]) -> dict[str, Any]:
    entry = _FACT_IDS.get(engine)
    if entry is None:
        return {}
    kind, field = entry
    for f in facts:
        if f.get("kind") == kind:
            value = (f.get("payload") or {}).get(field)
            if value:
                return {field: value}
    return {}


def resolve(stages: list[dict[str, Any]], roots: dict[str, str],
            facts: list[dict[str, Any]] | None = None) -> list[ResolvedArtifact]:
    """Every artifact a run produced, recorded ones first.

    `stages` are the export's stage records. A stage that recorded artifacts is
    taken at its word; one that did not is resolved from the ids it did record,
    and says so. `facts` is the last resort — the flagship run recorded neither
    artifacts nor `produced`, and its outputs would otherwise be unreachable
    despite the engines having plainly announced them at the time.
    """
    facts = facts or []
    out: list[ResolvedArtifact] = []
    for stage in stages:
        engine = stage.get("engine", "")
        seq = int(stage.get("seq", -1))

        recorded = stage.get("artifacts") or []
        if recorded:
            for a in recorded:
                p = Path(a.get("path", ""))
                exists, size, count = _measure(p)
                out.append(ResolvedArtifact(
                    kind=a.get("kind", ""), path=str(p),
                    description=a.get("description", ""), engine=engine,
                    stage_seq=seq, origin="recorded", exists=exists,
                    size_bytes=size, file_count=count))
            continue

        produced = stage.get("produced") or {}
        if not produced:
            produced = _ids_from_facts(engine, facts)
        guess = _by_convention(engine, produced, roots)
        if guess is None:
            continue
        path, kind = guess
        exists, size, count = _measure(Path(path))
        out.append(ResolvedArtifact(
            kind=kind, path=path,
            description=f"{kind} from {engine} (path derived, not recorded)",
            engine=engine, stage_seq=seq, origin="convention",
            exists=exists, size_bytes=size, file_count=count))
    return out


def engine_roots() -> dict[str, str]:
    """Engine key -> that engine's storage root.

    Reads the layout rather than the topology file: where an engine keeps its
    outputs is a property of this installation, not of how members happen to
    be addressed on the network.
    """
    return {key: str(engine_storage(key)) for key in ENGINE_KEYS}
