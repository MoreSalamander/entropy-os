"""A Claude-backed `LLMClient` — the cloud half of the backend toggle.

The engines talk to models through a four-method Protocol
(`entropy_os.engines.research.llm.client.LLMClient`): `chat_json`, `chat_text`, `embed`,
`available`. That protocol is small enough to implement against a different
provider without touching an engine, which is the whole reason this file can
exist alongside four untouched repositories.

Three things are load-bearing here.

**`chat_json` must stay schema-constrained.** The engines' design law is that
the model only ever *proposes* and a deterministic validator decides. Ollama
enforces the JSON schema server-side via its `format` parameter; the Anthropic
equivalent is structured outputs (`output_config.format`). Mapping one to the
other keeps the guarantee intact. Dropping to "please reply in JSON" prose
would quietly move this system from constrained output to hopeful output.

**Anthropic's schema dialect is narrower than Ollama's.** Structured outputs
reject the numeric and string constraints Ollama happily ignores, and require
`additionalProperties: false` on every object. The engines wrote their schemas
against Ollama, so schemas are adapted on the way out rather than the engines
being edited to suit a backend they should not know about.

**A refusal is not a crash.** Claude Opus 5 runs safety classifiers that can
decline a request, returning HTTP 200 with `stop_reason: "refusal"`. Research
topics are arbitrary user text, so this is a live possibility rather than a
theoretical one. It is translated into `LLMUnavailable` — the same signal a
down provider raises — because the engines already degrade honestly on that
and must never receive a refusal as if it were content.
"""

from __future__ import annotations

import json
from typing import Any

from .spec import LLMSpec

# The engines all import their LLM types from entropy_os.engines.research, so there is
# exactly one LLMUnavailable class in play and raising it is what makes their
# existing degradation paths (e.g. VectorIndex falling back to exact-match
# entity resolution) actually catch. Outside an engine venv — one-engine's own
# test environment — a local stand-in keeps this module importable.
try:                                          # pragma: no cover - env dependent
    from entropy_os.engines.research.llm.client import LLMUnavailable
except ImportError:                           # pragma: no cover - env dependent
    class LLMUnavailable(RuntimeError):
        """Provider unreachable, refusing, or misconfigured."""

# Structured-output keywords Anthropic does not accept. Ollama tolerates them,
# so engine schemas contain them; sending them through yields a 400 that reads
# like a bug in the engine rather than a dialect difference.
_UNSUPPORTED_KEYWORDS = frozenset({
    "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf",
    "minLength", "maxLength", "pattern", "minItems", "maxItems", "uniqueItems",
    "minProperties", "maxProperties", "default", "examples",
})

# Thinking is on by default on Opus 5 and is charged against max_tokens along
# with the response, so both ceilings leave headroom for it. Requests stream,
# which is what keeps a large ceiling from tripping the SDK's own long-request
# guard.
JSON_MAX_TOKENS = 32_000
TEXT_MAX_TOKENS = 64_000

FALLBACK_BETA = "server-side-fallback-2026-07-01"


def adapt_schema(schema: Any) -> Any:
    """Rewrite an Ollama-dialect JSON schema into one Anthropic will accept.

    Recursive, and deliberately lossy in one direction only: constraints are
    dropped, never invented. A dropped `maxLength` means the model is less
    tightly bounded than the engine asked for — the engine's own validator
    still runs afterwards, so the guarantee is preserved where it counts.
    """
    if isinstance(schema, list):
        return [adapt_schema(item) for item in schema]
    if not isinstance(schema, dict):
        return schema

    out: dict[str, Any] = {}
    for key, value in schema.items():
        if key in _UNSUPPORTED_KEYWORDS:
            continue
        if key in ("properties", "$defs", "definitions") and isinstance(value, dict):
            out[key] = {k: adapt_schema(v) for k, v in value.items()}
        elif key in ("items", "additionalItems", "not"):
            out[key] = adapt_schema(value)
        elif key in ("anyOf", "allOf", "oneOf") and isinstance(value, list):
            out[key] = [adapt_schema(v) for v in value]
        else:
            out[key] = adapt_schema(value) if isinstance(value, (dict, list)) else value

    if out.get("type") == "object" or "properties" in out:
        # Required by structured outputs, and harmless where the engine did
        # not think to say it: these schemas describe closed records already.
        out["additionalProperties"] = False
        if "properties" in out and "required" not in out:
            out["required"] = list(out["properties"].keys())
    return out


class ClaudeClient:
    """Implements the engines' LLMClient protocol against the Anthropic API."""

    def __init__(self, spec: LLMSpec):
        self.spec = spec
        self._sdk = None
        # Set once a request proves the fallbacks beta is not enabled for this
        # account, so the whole run stops paying a failed first attempt.
        self._fallbacks_ok = spec.claude_fallbacks

    @property
    def _client(self):
        """Built on first use, not at construction.

        Selecting a backend must not require the SDK to be importable — and
        more importantly, a missing package should surface as `LLMUnavailable`
        at the first model call, where every engine already degrades, rather
        than as an exception during engine construction that takes the whole
        adapter down before it can do any of its deterministic work.
        """
        if self._sdk is None:
            try:
                from anthropic import AsyncAnthropic
            except ImportError as e:            # pragma: no cover - env dependent
                raise LLMUnavailable(
                    "the claude backend needs the `anthropic` package, and "
                    "adapters run inside each engine's own venv — install it "
                    "there (<engine>/.venv/bin/pip install anthropic) or set "
                    "ONE_ENGINE_LLM_BACKEND=local") from e
            # An empty key is not passed through: the SDK resolves the
            # credential itself from ANTHROPIC_API_KEY or a stored
            # `ant auth login` profile, and overriding that with "" would
            # break the profile path.
            self._sdk = (AsyncAnthropic(api_key=self.spec.claude_api_key)
                         if self.spec.claude_api_key else AsyncAnthropic())
        return self._sdk

    # ----------------------------------------------------------------- #
    # the protocol
    # ----------------------------------------------------------------- #

    async def available(self) -> bool:
        """Cheap liveness + credential check.

        Retrieving the model validates the key, the model id, and reachability
        in one call, without spending generation tokens.
        """
        try:
            await self._client.models.retrieve(self.spec.model_for("extract"))
            return True
        except Exception:      # noqa: BLE001 — any failure means "not usable"
            return False

    async def chat_json(self, role: str, system: str, user: str,
                        schema: dict[str, Any]) -> dict[str, Any]:
        text = await self._message(
            role, system, user, max_tokens=JSON_MAX_TOKENS,
            output_config={"format": {"type": "json_schema",
                                      "schema": adapt_schema(schema)}})
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            # Structured output should always parse. If it does not, that is a
            # provider fault, and the caller's validator handles the empty case
            # — the same contract OllamaClient offers.
            raise LLMUnavailable(f"non-JSON structured output: {e}") from e

    async def chat_text(self, role: str, system: str, user: str) -> str:
        return await self._message(role, system, user,
                                   max_tokens=TEXT_MAX_TOKENS)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Not available from Anthropic — see the module docstring.

        Raising is the honest answer, and the engines are built for it:
        `VectorIndex` catches `LLMUnavailable` and degrades to exact-match
        entity resolution. Use `HybridClient` to keep real embeddings from a
        local model while chat runs on Claude.
        """
        raise LLMUnavailable(
            "the Anthropic API publishes no embeddings endpoint; pair this "
            "client with a local embedder (HybridClient) or accept "
            "exact-match entity resolution")

    async def aclose(self) -> None:
        # Only if a client was ever built — closing would otherwise construct
        # one just to close it, and fail when the SDK is absent.
        if self._sdk is not None:
            await self._sdk.close()

    # ----------------------------------------------------------------- #
    # internals
    # ----------------------------------------------------------------- #

    def _request(self, role: str, system: str, user: str, max_tokens: int,
                 output_config: dict | None) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model": self.spec.model_for(role),
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        cfg = dict(output_config or {})
        if self.spec.claude_effort:
            cfg["effort"] = self.spec.claude_effort
        if cfg:
            kwargs["output_config"] = cfg
        return kwargs

    async def _message(self, role: str, system: str, user: str,
                       max_tokens: int,
                       output_config: dict | None = None) -> str:
        kwargs = self._request(role, system, user, max_tokens, output_config)
        try:
            message = await self._send(kwargs, with_fallbacks=self._fallbacks_ok)
        except LLMUnavailable:
            raise
        except Exception as e:                  # noqa: BLE001
            if self._fallbacks_ok and _is_fallback_rejection(e):
                # The account does not have the fallbacks beta. That is a
                # configuration fact, not a reason to fail the run — drop the
                # parameter for the rest of this client's life and retry once.
                self._fallbacks_ok = False
                message = await self._send(kwargs, with_fallbacks=False)
            else:
                raise LLMUnavailable(f"claude request failed: {e}") from e

        if getattr(message, "stop_reason", None) == "refusal":
            details = getattr(message, "stop_details", None)
            category = getattr(details, "category", None) or "unspecified"
            raise LLMUnavailable(
                f"claude declined this request (category: {category}); "
                "the run degrades rather than fabricating a response")

        return "".join(block.text for block in message.content
                       if getattr(block, "type", None) == "text")

    async def _send(self, kwargs: dict[str, Any], with_fallbacks: bool):
        """One streamed request. Streaming avoids the SDK's long-request guard
        at these token ceilings, and `get_final_message()` gives back the whole
        message once it lands."""
        if with_fallbacks:
            # A policy decline is re-served by another model inside the same
            # call, so an arbitrary research topic that trips a classifier
            # does not take a multi-stage composed run down with it.
            async with self._client.beta.messages.stream(
                    betas=[FALLBACK_BETA], fallbacks="default", **kwargs) as s:
                return await s.get_final_message()
        async with self._client.messages.stream(**kwargs) as s:
            return await s.get_final_message()


def _is_fallback_rejection(exc: Exception) -> bool:
    """Whether a failure is specifically about the fallbacks beta."""
    text = str(exc).lower()
    return "fallback" in text and ("beta" in text or "400" in text
                                   or "invalid" in text)
