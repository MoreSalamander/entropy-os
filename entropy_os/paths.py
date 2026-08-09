"""Where everything lives, decided once.

Each component absorbed into Entropy OS arrived with its own notion of "the
repo root" — `Path(__file__).parent.parent`, computed independently in five
places and correct only while each package sat at the top of its own
repository. Under one roof those anchors all resolve somewhere different and
all resolve wrong, so the layout stops being an accident of nesting depth and
becomes a fact stated here.

The storage split mirrors the architecture rather than the history. Composition
owns the durable record of *runs that crossed engines* (the event log, the
Temporal dev database, adapter pids and logs); each engine owns the knowledge
it accumulates on its own (knowledge graph, vector store, generated artifacts).
An engine's storage is addressed by its CONTRACT member key — research,
software, university, web — not by the repository it used to be, because the
member key is the name the rest of the system knows it by.

`ENTROPY_STORAGE` relocates all of it. The hosted face runs with a mounted
volume that is not inside the checkout, and nothing here may assume otherwise.
"""

from __future__ import annotations

import os
from pathlib import Path

# entropy_os/paths.py -> entropy_os/ -> the checkout.
REPO_ROOT = Path(__file__).resolve().parent.parent

# Configuration is version-controlled and lives INSIDE the package, not beside
# it. A checkout has both; an installed wheel has only what the package
# carries, and a config resolved from the checkout root simply is not there
# once this is pip-installed — which is how the composite came to boot fine
# locally and crash hosted on a file it could not find.
#
# ENTROPY_CONFIG_DIR points at operator-supplied configuration instead, for a
# deployment that wants to wire members differently without a rebuild.
_CONFIG_OVERRIDE = os.environ.get("ENTROPY_CONFIG_DIR", "").strip()
CONFIG_DIR = (Path(_CONFIG_OVERRIDE).expanduser().resolve()
              if _CONFIG_OVERRIDE else Path(__file__).resolve().parent / "config")

COMPOSITION_CONFIG = CONFIG_DIR / "composition.yaml"
RESEARCH_CONFIG = CONFIG_DIR / "research.yaml"


def _storage_root() -> Path:
    override = os.environ.get("ENTROPY_STORAGE", "").strip()
    return Path(override).expanduser().resolve() if override else REPO_ROOT / "storage_data"


STORAGE_ROOT = _storage_root()

# Composition-level durable state: the unified event log, the orchestrator's
# dev database, and the launcher's pid/log files.
COMPOSITION_STORAGE = STORAGE_ROOT
EVENTS_LOG = STORAGE_ROOT / "events.jsonl"

# The contract member keys, in the order the composed pipelines run them.
ENGINE_KEYS = ("research", "software", "university", "web")


def engine_storage(member_key: str) -> Path:
    """The storage root for one engine, addressed by its contract member key.

    Created on demand: an engine that has never run has no directory, and a
    caller that is about to write should not have to care which case it is in.
    """
    if member_key not in ENGINE_KEYS:
        raise ValueError(
            f"unknown engine member key {member_key!r}; expected one of {ENGINE_KEYS}")
    path = STORAGE_ROOT / "engines" / member_key
    path.mkdir(parents=True, exist_ok=True)
    return path
