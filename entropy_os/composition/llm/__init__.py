"""Model backend selection — local Ollama or the Claude API, per run.

`build_llm(spec)` returns something satisfying the engines' `LLMClient`
protocol, or `None` to mean "let the engine construct its own client". `None`
is the default and is not a failure case: it is how the local path stays
byte-for-byte the behaviour that already runs on this laptop, with no client
injected and nothing intercepted.

    from entropy_os.composition.llm import build_llm, spec_from_env

    engine = Engine(llm=build_llm())          # env decides; None → engine's own

Selection is a per-run value rather than a process-wide switch, which is what
lets a hosted deployment serve one visitor's credential without changing the
next visitor's run.
"""

from collections.abc import Callable
from dataclasses import replace
from typing import Any

from .hybrid import HybridClient, OllamaEmbedder, RoutedClient, build_hybrid
from .settings import active_spec
from .spec import DEFAULT_CLAUDE_MODEL, ROLES, LLMSpec, spec_from_env

__all__ = ["DEFAULT_CLAUDE_MODEL", "HybridClient", "LLMSpec", "OllamaEmbedder",
           "ROLES", "RoutedClient", "active_spec", "build_hybrid", "build_llm",
           "describe_backend", "spec_from_env"]

# The convention three of the four engines use for their own local client. Only
# consulted when a mixed run needs a local half and the adapter did not supply
# one — research-engine loads its own config, so its adapter passes that in.
_LOCAL_TIMEOUT_S = 300


def _default_local() -> Any:
    from entropy_os.engines.research.llm.client import LLMConfig, OllamaClient
    return OllamaClient(LLMConfig(timeout_s=_LOCAL_TIMEOUT_S))


def _credentialed(spec: LLMSpec) -> LLMSpec:
    """Fill in the stored credential when a cloud-routed run has none.

    Deliberately *not* `spec.with_key()`: that promotes an all-local run to the
    cloud when handed a key, which is right for "a visitor supplied their own"
    and wrong here. The presence of a key in the operator's Keychain is not a
    request to start spending it — only the routing decides that.
    """
    if spec.claude_api_key or not spec.any_cloud:
        return spec
    try:
        from engine import credentials
    except ImportError:                    # pragma: no cover - env dependent
        return spec                        # no veritas here; SDK resolves it
    key = credentials.resolve()
    return replace(spec, claude_api_key=key) if key else spec


def _pin_local(client: Any, spec: LLMSpec) -> Any:
    """Re-point a local client at the operator's chosen models.

    Rebuilt from a *copy* of the engine's config rather than mutated in place:
    the adapter hands its engine the very same config object, so writing into
    it would edit the engine's own settings as a side effect of building a
    client. The base URL is baked into the HTTP client at construction, which
    is the other reason a copy-and-rebuild is the honest operation here.
    """
    cfg = getattr(client, "cfg", None)
    if cfg is None or not spec.has_local_overrides:
        return client
    from entropy_os.engines.research.llm.client import OllamaClient

    cfg = cfg.model_copy(deep=True)
    for role, model in spec.local_models.items():
        setattr(cfg.roles, role, model)
    if spec.local_base_url:
        cfg.base_url = spec.local_base_url
    return OllamaClient(cfg)


def build_llm(spec: LLMSpec | None = None,
              local: Callable[[], Any] | None = None):
    """The client for this run, or None to defer to the engine's own default.

    Three outcomes, and the first is the one that runs every day:

    * **nothing routed to the cloud → None.** one-engine could construct an
      `OllamaClient` itself, but then every engine's carefully tuned local
      defaults — timeouts, role→model routing, the embed model — would silently
      come from here instead of from the engine that owns them. Deferring keeps
      the local path exactly as the engines built it.
    * **every role routed to the cloud → a HybridClient.** Claude for chat,
      local embeddings, because Anthropic publishes no embeddings endpoint.
    * **some roles routed → a RoutedClient**, holding both. This is the only
      case where one-engine constructs a local client itself, and it is why
      `local` exists: an adapter that knows its engine's convention passes it,
      so the local half stays the client the engine would have built.

    A local *pin* — the operator naming a different Ollama model for a role —
    is the one thing that turns the first outcome into a real client: there is
    no way to honour "run judge on gemma4 instead" while injecting nothing.
    The client is still built from the engine's own config, so everything the
    operator did not name stays exactly as the engine set it.
    """
    spec = _credentialed(spec if spec is not None else active_spec())
    if not spec.any_cloud:
        return _pin_local((local or _default_local)(), spec) \
            if spec.has_local_overrides else None
    if not spec.is_mixed:
        return build_hybrid(spec)

    from .claude import ClaudeClient
    return RoutedClient(_pin_local((local or _default_local)(), spec),
                        ClaudeClient(spec), spec)


def describe_backend(spec: LLMSpec | None = None) -> str:
    """Human-readable backend summary for health output. Never shows a key."""
    return (spec if spec is not None else active_spec()).describe()
