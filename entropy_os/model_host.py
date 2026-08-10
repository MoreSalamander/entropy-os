"""What the machine underneath can offer a model runner: a credential, and a
local model daemon. Answered here so the front door never has to care which.

Both answers really live in veritas (`engine.credentials`, `engine.catalog`),
which is where providers are built. This module exists because of two facts
about the boundary between the repositories, and the second one cost a
deployment.

**The two hosts are not alike.** A laptop keeps its Anthropic key in the macOS
Keychain and runs Ollama beside the app. A Fly Machine is Linux: `security`
does not exist and never will, there is no GPU and so no Ollama, and the key
arrives as an environment variable from `fly secrets`. Code that assumes the
first host is wrong on the second, and vice versa.

**entropy-os pins veritas by tag.** The hosted image installs a *released*
engine, so anything here that reaches into the engine must tolerate an engine
that predates it. It did not, once: `from engine import credentials` at module
scope crashed the hosted front door on import, and the bare-install smoke test
missed it because that test installs veritas from the sibling checkout — the
one place the new module existed.

So every entry point below prefers the engine's implementation and falls back
to something honest when the installed engine has no such thing. On the host
where that fallback runs, it is not a degradation: reading the environment IS
how the credential arrives there.
"""

from __future__ import annotations

import os
from typing import Any

ENV_VAR = "ANTHROPIC_API_KEY"


def _engine_credentials() -> Any | None:
    try:
        from engine import credentials
    except ImportError:      # an engine released before the module existed
        return None
    return credentials


def resolve_key() -> str:
    """The Anthropic key for this run, or "" when there is none.

    Empty is a legitimate answer: the SDK does its own resolution, so handing
    it nothing means "use whatever you already know about".
    """
    if (impl := _engine_credentials()) is not None:
        return impl.resolve()
    return os.environ.get(ENV_VAR, "").strip()


def key_status() -> dict[str, Any]:
    """Whether a credential exists and where from — never the value."""
    if (impl := _engine_credentials()) is not None:
        return dict(impl.status())
    env = os.environ.get(ENV_VAR, "").strip()
    return {
        "present": bool(env),
        "source": "environment" if env else "none",
        "tail": env[-4:] if env else "",
        # No Keychain here, so there is nowhere for a pasted key to go that
        # would outlive the process. Saying so is better than accepting one
        # and losing it at the next restart.
        "editable": False,
        "note": "this host stores no keys; set ANTHROPIC_API_KEY in its "
                "environment (on Fly: fly secrets set)",
    }


def store_key(value: str) -> None:
    impl = _engine_credentials()
    if impl is None:
        raise NotImplementedError(
            "this host has no key store; set ANTHROPIC_API_KEY in its "
            "environment instead")
    impl.store(value)


def forget_key() -> bool:
    impl = _engine_credentials()
    return False if impl is None else impl.forget()


def local_inventory() -> dict[str, Any]:
    """What the local model daemon has pulled, if there is one at all."""
    try:
        from engine.catalog import local_inventory as engine_inventory
    except ImportError:      # released engine without the probe
        return {"running": False,
                "url": os.environ.get("OLLAMA_HOST", "http://localhost:11434"),
                "installed": []}
    return dict(engine_inventory())
