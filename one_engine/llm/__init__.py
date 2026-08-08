"""Model backend selection — local Ollama or the Claude API, per run.

`build_llm(spec)` returns something satisfying the engines' `LLMClient`
protocol, or `None` to mean "let the engine construct its own client". `None`
is the default and is not a failure case: it is how the local path stays
byte-for-byte the behaviour that already runs on this laptop, with no client
injected and nothing intercepted.

    from one_engine.llm import build_llm, spec_from_env

    engine = Engine(llm=build_llm())          # env decides; None → engine's own

Selection is a per-run value rather than a process-wide switch, which is what
lets a hosted deployment serve one visitor's credential without changing the
next visitor's run.
"""

from .hybrid import HybridClient, OllamaEmbedder, build_hybrid
from .spec import DEFAULT_CLAUDE_MODEL, ROLES, LLMSpec, spec_from_env

__all__ = ["DEFAULT_CLAUDE_MODEL", "HybridClient", "LLMSpec", "OllamaEmbedder",
           "ROLES", "build_hybrid", "build_llm", "describe_backend",
           "spec_from_env"]


def build_llm(spec: LLMSpec | None = None):
    """The client for this run, or None to defer to the engine's own default.

    Returning None for the local backend is deliberate. one-engine could
    construct an `OllamaClient` itself and pass it in, but then every engine's
    carefully tuned local defaults — timeouts, role→model routing, the embed
    model — would silently come from here instead of from the engine that owns
    them. Deferring keeps the local path exactly as the engines built it.
    """
    spec = spec or spec_from_env()
    if spec.backend == "claude":
        return build_hybrid(spec)
    return None


def describe_backend(spec: LLMSpec | None = None) -> str:
    """Human-readable backend summary for health output. Never shows a key."""
    return (spec or spec_from_env()).describe()
