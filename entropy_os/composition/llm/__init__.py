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
from typing import Any

from .hybrid import HybridClient, OllamaEmbedder, RoutedClient, build_hybrid
from .spec import DEFAULT_CLAUDE_MODEL, ROLES, LLMSpec, spec_from_env

__all__ = ["DEFAULT_CLAUDE_MODEL", "HybridClient", "LLMSpec", "OllamaEmbedder",
           "ROLES", "RoutedClient", "build_hybrid", "build_llm",
           "describe_backend", "spec_from_env"]

# The convention three of the four engines use for their own local client. Only
# consulted when a mixed run needs a local half and the adapter did not supply
# one — research-engine loads its own config, so its adapter passes that in.
_LOCAL_TIMEOUT_S = 300


def _default_local() -> Any:
    from entropy_os.engines.research.llm.client import LLMConfig, OllamaClient
    return OllamaClient(LLMConfig(timeout_s=_LOCAL_TIMEOUT_S))


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
    """
    spec = spec or spec_from_env()
    if not spec.any_cloud:
        return None
    if not spec.is_mixed:
        return build_hybrid(spec)

    from .claude import ClaudeClient
    return RoutedClient((local or _default_local)(), ClaudeClient(spec), spec)


def describe_backend(spec: LLMSpec | None = None) -> str:
    """Human-readable backend summary for health output. Never shows a key."""
    return (spec or spec_from_env()).describe()
