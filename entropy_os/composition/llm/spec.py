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
    # Roles that go to Claude while everything else stays local. This is the
    # interesting case, not a convenience: `judge` is the role that grades what
    # the other roles proposed, so routing only it to a stronger model buys
    # scrutiny exactly where the thesis puts the weight, and leaves the bulk
    # extraction work local and free.
    cloud_roles: frozenset[str] = frozenset()
    claude_models: dict[str, str] = field(default_factory=dict)
    claude_api_key: str = ""               # empty → the SDK's own resolution
    claude_effort: str = ""                # "" → the API's default
    claude_fallbacks: bool = True
    # Embeddings when the chat backend has none of its own. Empty disables
    # them, which makes semantic entity resolution degrade to exact match —
    # the engines already handle that path, so it fails honestly.
    embed_base_url: str = "http://localhost:11434"
    embed_model: str = "nomic-embed-text"
    # Local role→model overrides. Empty is the important default: it means
    # "the engine's own config decides", which is what keeps `build_llm()`
    # able to return None and leave the local path untouched. A single entry
    # here is enough to make one-engine construct the local client itself, so
    # this dict is never populated speculatively.
    local_models: dict[str, str] = field(default_factory=dict)
    local_base_url: str = ""               # "" → the engine's own base URL

    def model_for(self, role: str) -> str:
        return self.claude_models.get(role, DEFAULT_CLAUDE_MODEL)

    @property
    def has_local_overrides(self) -> bool:
        return bool(self.local_models) or bool(self.local_base_url)

    def fingerprint(self) -> str:
        """A stable identity for "which models does this run use?".

        Adapters cache their engine — an engine construction loads a knowledge
        graph and a vector index, so rebuilding per request is not an option.
        That cache has to be invalidated when the routing changes, and the
        comparison must ignore the credential: a rotated key is the same
        routing and must not throw away a loaded graph.
        """
        return "|".join((
            self.backend,
            ",".join(sorted(self.cloud_roles)),
            ",".join(f"{r}={self.claude_models[r]}" for r in sorted(self.claude_models)),
            ",".join(f"{r}={self.local_models[r]}" for r in sorted(self.local_models)),
            self.local_base_url, self.claude_effort,
            self.embed_base_url, self.embed_model,
            "fb" if self.claude_fallbacks else "-",
        ))

    def routes_to_cloud(self, role: str) -> bool:
        return self.backend == "claude" or role in self.cloud_roles

    @property
    def any_cloud(self) -> bool:
        return self.backend == "claude" or bool(self.cloud_roles)

    @property
    def is_mixed(self) -> bool:
        """Some roles cloud, some local — the case that needs both clients."""
        return (self.backend != "claude" and bool(self.cloud_roles)
                and not self.cloud_roles.issuperset(ROLES))

    def with_key(self, api_key: str) -> LLMSpec:
        """A copy that uses a caller-supplied credential.

        This is the hook a hosted deployment needs: the same default spec, one
        run's key, never written back to the process environment and never
        shared with the next run.

        Supplying a key does not escalate an already-routed run: if some roles
        were deliberately kept local, "here is a credential" must not silently
        promote the whole run to the cloud. It only turns on the cloud when
        nothing was routed there yet.
        """
        backend = self.backend if self.any_cloud else "claude"
        return replace(self, claude_api_key=api_key, backend=backend)

    def describe(self) -> str:
        """Operator-readable summary. Never includes the credential."""
        pinned = ", ".join(f"{r}→{self.local_models[r]}"
                           for r in ROLES if r in self.local_models)
        note = f" [{pinned}]" if pinned else ""
        if not self.any_cloud:
            return f"local (ollama){note}"
        source = "caller-supplied key" if self.claude_api_key else "environment"
        cloud = [r for r in ROLES if self.routes_to_cloud(r)]
        models = sorted({self.model_for(r) for r in cloud})
        where = "all roles" if len(cloud) == len(ROLES) else "+".join(cloud)
        local = [r for r in ROLES if not self.routes_to_cloud(r)]
        rest = f"; local: {'+'.join(local)}{note}" if local else ""
        embed = f"{self.embed_model} @ {self.embed_base_url}" \
            if self.embed_base_url else "disabled"
        return (f"claude [{', '.join(models)}] for {where} via {source}{rest}; "
                f"embeddings: {embed}")


def spec_from_env() -> LLMSpec:
    """The deployment's default spec.

    Defaults to local, so nothing about an existing laptop run changes: the
    engines keep constructing their own Ollama clients unless something here
    explicitly says otherwise.

        ONE_ENGINE_LLM_BACKEND        local (default) | claude
        ONE_ENGINE_CLAUDE_ROLES       roles to send to Claude while the rest
                                      stay local, e.g. "judge"
        ANTHROPIC_API_KEY             read by the SDK; never logged or echoed
        ONE_ENGINE_CLAUDE_MODEL       one model for every role
        ONE_ENGINE_CLAUDE_MODEL_JUDGE per-role override (…_EXTRACT, _PLAN,
                                      _SUMMARIZE, _LIGHT)
        ONE_ENGINE_CLAUDE_EFFORT      low|medium|high|xhigh|max
        ONE_ENGINE_CLAUDE_FALLBACKS   0 disables server-side refusal fallback
        ONE_ENGINE_EMBED_URL          embeddings host (default local ollama)
        ONE_ENGINE_EMBED_MODEL        empty disables embeddings entirely
        ONE_ENGINE_LOCAL_MODEL_JUDGE  pin one role's LOCAL model, overriding the
                                      engine's own config (also …_EXTRACT,
                                      _PLAN, _SUMMARIZE, _LIGHT)
        ONE_ENGINE_LOCAL_URL          Ollama host for the local half
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

    # Unknown role names are dropped rather than carried: a typo'd role would
    # otherwise look configured while silently routing nothing.
    requested = {r.strip().lower()
                 for r in os.environ.get("ONE_ENGINE_CLAUDE_ROLES", "").split(",")}
    cloud_roles = frozenset(r for r in requested if r in ROLES)

    # Local pins are read the same way and, like the cloud ones, only exist
    # when named: an empty dict means "the engine's own config decides", which
    # is the default that keeps the local path byte-for-byte what it was.
    local_models: dict[str, str] = {}
    for role in ROLES:
        pinned = os.environ.get(f"ONE_ENGINE_LOCAL_MODEL_{role.upper()}", "").strip()
        if pinned:
            local_models[role] = pinned

    return LLMSpec(
        backend=backend,
        cloud_roles=cloud_roles,
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
        local_models=local_models,
        local_base_url=os.environ.get("ONE_ENGINE_LOCAL_URL", "").strip(),
    )
