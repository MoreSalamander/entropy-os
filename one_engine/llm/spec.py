"""Which model backend a run uses — and where its credential comes from.

The four engines each accept `llm: LLMClient | None` and otherwise construct
their own `OllamaClient`. That parameter is the seam: supplying a client from
the adapter selects the backend without editing a single engine file, which is
the same mechanism the research timeout fix already uses.

Two facts shape this module.

**Backend selection is per run, not per process.** Reading the environment at
import time would be simpler, but it hard-codes an assumption that every run on
this host uses the same model and the same credential. A hosted deployment
breaks that assumption immediately: one visitor supplies a key, the next
supplies none. So the environment produces a *default* spec, and any caller
may hand in a different one for a single execution.

**Chat and embeddings are separate axes.** Ollama serves both; the Anthropic
API documents no embeddings endpoint (its published surface is Messages,
Batches, Files, Token Counting and Models — there is no embeddings route and
no embedding model in the catalog). So "use Claude" cannot mean "use Claude for
everything": it means Claude for `chat_json`/`chat_text`, and something else —
normally a local `nomic-embed-text` — for `embed`. That is why `LLMSpec` names
the two independently instead of pretending one switch covers both.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, replace

# Roles the engines actually ask for. Ollama routes each to a different local
# model (judge deliberately separated from extract, so the model that grades a
# claim is not the model that produced it). That separation is a property of
# the thesis, not of Ollama, so the cloud backend preserves it: `judge` is
# addressed as its own role even when every role resolves to the same model.
ROLES = ("extract", "plan", "judge", "summarize", "light")

# One model for every role unless the operator says otherwise. Deliberately not
# downgraded per role to save money — which role deserves a cheaper model is a
# judgment about the operator's own cost/quality tradeoff, so it is theirs to
# make via ONE_ENGINE_CLAUDE_MODEL_<ROLE>, not a default chosen for them.
DEFAULT_CLAUDE_MODEL = "claude-opus-5"


@dataclass(frozen=True)
class LLMSpec:
    """A complete answer to "what runs the models for this execution?".

    Frozen because a spec is attached to a run: a run that silently changed
    backend halfway through would make its own provenance a lie.
    """

    backend: str = "local"                 # "local" | "claude"
    claude_models: dict[str, str] = field(default_factory=dict)
    claude_api_key: str = ""               # empty → the SDK's own resolution
    claude_effort: str = ""                # "" → the API's default
    claude_fallbacks: bool = True
    # Embeddings when the chat backend has none of its own. Empty disables
    # them, which makes semantic entity resolution degrade to exact match —
    # the engines already handle that path, so it fails honestly.
    embed_base_url: str = "http://localhost:11434"
    embed_model: str = "nomic-embed-text"

    def model_for(self, role: str) -> str:
        return self.claude_models.get(role, DEFAULT_CLAUDE_MODEL)

    def with_key(self, api_key: str) -> LLMSpec:
        """A copy that uses a caller-supplied credential.

        This is the hook a hosted deployment needs: the same default spec, one
        run's key, never written back to the process environment and never
        shared with the next run.
        """
        return replace(self, claude_api_key=api_key, backend="claude")

    def describe(self) -> str:
        """Operator-readable summary. Never includes the credential."""
        if self.backend == "local":
            return "local (ollama)"
        source = "caller-supplied key" if self.claude_api_key else "environment"
        models = sorted(set(self.model_for(r) for r in ROLES))
        embed = f"{self.embed_model} @ {self.embed_base_url}" \
            if self.embed_base_url else "disabled"
        return f"claude [{', '.join(models)}] via {source}; embeddings: {embed}"


def spec_from_env() -> LLMSpec:
    """The deployment's default spec.

    Defaults to local, so nothing about an existing laptop run changes: the
    engines keep constructing their own Ollama clients unless something here
    explicitly says otherwise.

        ONE_ENGINE_LLM_BACKEND        local (default) | claude
        ANTHROPIC_API_KEY             read by the SDK; never logged or echoed
        ONE_ENGINE_CLAUDE_MODEL       one model for every role
        ONE_ENGINE_CLAUDE_MODEL_JUDGE per-role override (…_EXTRACT, _PLAN,
                                      _SUMMARIZE, _LIGHT)
        ONE_ENGINE_CLAUDE_EFFORT      low|medium|high|xhigh|max
        ONE_ENGINE_CLAUDE_FALLBACKS   0 disables server-side refusal fallback
        ONE_ENGINE_EMBED_URL          embeddings host (default local ollama)
        ONE_ENGINE_EMBED_MODEL        empty disables embeddings entirely
    """
    backend = os.environ.get("ONE_ENGINE_LLM_BACKEND", "local").strip().lower()
    if backend not in ("local", "claude"):
        backend = "local"

    shared = os.environ.get("ONE_ENGINE_CLAUDE_MODEL", "").strip()
    models: dict[str, str] = {}
    for role in ROLES:
        per_role = os.environ.get(f"ONE_ENGINE_CLAUDE_MODEL_{role.upper()}",
                                  "").strip()
        chosen = per_role or shared
        if chosen:
            models[role] = chosen

    return LLMSpec(
        backend=backend,
        claude_models=models,
        # Left empty on purpose: the Anthropic SDK resolves the credential
        # itself (env var, then an `ant auth login` profile). Reading the key
        # into our own object would put it in tracebacks and repr() output for
        # no benefit.
        claude_api_key="",
        claude_effort=os.environ.get("ONE_ENGINE_CLAUDE_EFFORT", "").strip(),
        claude_fallbacks=os.environ.get("ONE_ENGINE_CLAUDE_FALLBACKS",
                                        "1").strip() not in ("0", "false", "no"),
        embed_base_url=os.environ.get("ONE_ENGINE_EMBED_URL",
                                      "http://localhost:11434").strip(),
        embed_model=os.environ.get("ONE_ENGINE_EMBED_MODEL",
                                   "nomic-embed-text").strip(),
    )
