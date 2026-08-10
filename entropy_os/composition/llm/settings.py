"""Operator-chosen model routing, persisted, readable by every process.

`spec_from_env()` answers "what did the deployment start with". This module
answers the different question "what has the operator changed since", and the
distinction matters because of where the engines run: the four adapters are
separate processes on separate ports. A model switch made in the front door
cannot reach them through a module global, an environment variable, or a
process-wide singleton — the front door is not their process. It reaches them
through a file all five agree on, re-read per run.

Three properties are load-bearing.

**The file is an overlay, not a replacement.** It stores only the fields an
operator actually touched. Everything else keeps falling through to the
environment, so a deployment that sets `ONE_ENGINE_CLAUDE_ROLES` still means
what it said after someone changes an unrelated local model.

**No credential is written here.** The file sits in the data root next to run
records; a key in it would be a key in every backup of that directory. The
credential lives in the Keychain (`engine.credentials`) and is resolved at
build time, so this file can be read, copied, and diffed freely.

**A malformed file is not fatal.** It is operator-editable by design, and a
settings page that cannot load because someone left a trailing comma is a
worse failure than one that falls back to the environment and says so.
"""

from __future__ import annotations

import json
import os
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ...paths import STORAGE_ROOT
from .spec import ROLES, LLMSpec, spec_from_env

SETTINGS_PATH = Path(
    os.environ.get("ENTROPY_LLM_SETTINGS", "").strip()
    or STORAGE_ROOT / "llm_settings.json"
)

# Fields an operator may set through the settings surface. Anything outside
# this set in the file is ignored rather than applied: the file is editable by
# hand, and a typo must not become a silently-honoured configuration.
_SCALARS = ("backend", "claude_effort", "embed_base_url", "embed_model",
            "local_base_url")


def load() -> dict[str, Any]:
    """The raw overlay. `{}` when absent, unreadable, or not an object."""
    try:
        data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save(values: dict[str, Any]) -> dict[str, Any]:
    """Write the overlay, stamped, and hand back what was written."""
    values = dict(values)
    values["updated_at"] = datetime.now(UTC).isoformat()
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(json.dumps(values, indent=2, sort_keys=True),
                             encoding="utf-8")
    return values


def clear() -> None:
    """Drop every override — the deployment's environment decides again."""
    SETTINGS_PATH.unlink(missing_ok=True)


def _role_map(raw: Any) -> dict[str, str]:
    """Role→model, keeping only real roles. An unknown role name is dropped
    for the same reason `spec_from_env` drops one: a typo that looks
    configured but routes nothing is worse than a typo that does nothing."""
    if not isinstance(raw, dict):
        return {}
    return {r: str(m).strip() for r, m in raw.items()
            if r in ROLES and str(m).strip()}


def active_spec(base: LLMSpec | None = None) -> LLMSpec:
    """The environment's spec with the operator's overlay applied.

    This is what `build_llm()` uses by default. `spec_from_env()` is left
    exactly as it was — it still means "the environment, and nothing else" —
    because the whole point of a per-run spec is that callers can compose one
    themselves, and a function that secretly consulted disk would take that
    away.
    """
    spec = base or spec_from_env()
    values = load()
    if not values:
        return spec

    changes: dict[str, Any] = {}
    for field in _SCALARS:
        if field in values and isinstance(values[field], str):
            changes[field] = values[field].strip()
    if changes.get("backend") not in (None, "local", "claude"):
        changes.pop("backend")

    if "cloud_roles" in values and isinstance(values["cloud_roles"], list):
        changes["cloud_roles"] = frozenset(
            r for r in (str(x).strip().lower() for x in values["cloud_roles"])
            if r in ROLES)
    if "claude_models" in values:
        changes["claude_models"] = _role_map(values["claude_models"])
    if "local_models" in values:
        changes["local_models"] = _role_map(values["local_models"])
    if isinstance(values.get("claude_fallbacks"), bool):
        changes["claude_fallbacks"] = values["claude_fallbacks"]

    return replace(spec, **changes) if changes else spec
