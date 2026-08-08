"""LLM access layer: role-routed, schema-constrained, replaceable.

Design law: the LLM only ever PROPOSES. Every call site feeds the output
through a deterministic validator before anything is stored. To make that
enforceable, this client exposes exactly two operations:

  chat_json(role, ...)  -> dict constrained by a JSON schema (Ollama `format`)
  embed(texts)          -> list[list[float]]

There is deliberately no free-text generation path except `chat_text`, which
is used only for report prose — never for graph data.

FakeLLM implements the same interface for offline tests.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Protocol

import httpx

from ..config import LLMConfig


class LLMUnavailable(RuntimeError):
    """Raised when the provider is down or the model is missing.

    Callers degrade honestly (deterministic-only mode) instead of fabricating.
    """


class LLMClient(Protocol):
    async def chat_json(self, role: str, system: str, user: str,
                        schema: dict[str, Any]) -> dict[str, Any]: ...
    async def chat_text(self, role: str, system: str, user: str) -> str: ...
    async def embed(self, texts: list[str]) -> list[list[float]]: ...
    async def available(self) -> bool: ...


class OllamaClient:
    """Async Ollama client with role→model routing and structured outputs."""

    def __init__(self, cfg: LLMConfig):
        self.cfg = cfg
        self._client = httpx.AsyncClient(base_url=cfg.base_url,
                                         timeout=httpx.Timeout(cfg.timeout_s))
        self._models: set[str] | None = None

    def model_for(self, role: str) -> str:
        return getattr(self.cfg.roles, role, self.cfg.roles.extract)

    async def available(self) -> bool:
        try:
            r = await self._client.get("/api/tags")
            r.raise_for_status()
            self._models = {m["name"] for m in r.json().get("models", [])}
            return True
        except Exception:
            return False

    async def _chat(self, model: str, system: str, user: str,
                    fmt: dict[str, Any] | None) -> str:
        payload: dict[str, Any] = {
            "model": model,
            "stream": False,
            "options": {"temperature": self.cfg.temperature},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        if fmt is not None:
            payload["format"] = fmt  # Ollama enforces the JSON schema server-side
        for attempt in (1, 2):  # one retry on transient failure
            try:
                r = await self._client.post("/api/chat", json=payload)
                r.raise_for_status()
                return r.json()["message"]["content"]
            except (httpx.HTTPError, KeyError) as e:
                if attempt == 2:
                    raise LLMUnavailable(f"ollama chat failed for {model}: {e}") from e
                await asyncio.sleep(1.5)
        raise LLMUnavailable("unreachable")  # pragma: no cover

    async def chat_json(self, role: str, system: str, user: str,
                        schema: dict[str, Any]) -> dict[str, Any]:
        content = await self._chat(self.model_for(role), system, user, schema)
        try:
            return json.loads(content)
        except json.JSONDecodeError as e:
            # Schema-constrained output should always parse; if it doesn't,
            # that is a provider fault and the caller's validator handles {}.
            raise LLMUnavailable(f"non-JSON structured output: {e}") from e

    async def chat_text(self, role: str, system: str, user: str) -> str:
        return await self._chat(self.model_for(role), system, user, None)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        try:
            r = await self._client.post(
                "/api/embed", json={"model": self.cfg.embed_model, "input": texts})
            r.raise_for_status()
            return r.json()["embeddings"]
        except (httpx.HTTPError, KeyError) as e:
            raise LLMUnavailable(f"embed failed: {e}") from e

    async def aclose(self) -> None:
        await self._client.aclose()


class FakeLLM:
    """Deterministic stand-in for tests. Returns canned responses by role."""

    def __init__(self, json_responses: dict[str, list[dict]] | None = None,
                 text_response: str = "test prose", up: bool = True):
        self.json_responses = json_responses or {}
        self.text_response = text_response
        self.up = up
        self.calls: list[tuple[str, str]] = []  # (role, user) audit trail

    async def available(self) -> bool:
        return self.up

    async def chat_json(self, role: str, system: str, user: str,
                        schema: dict[str, Any]) -> dict[str, Any]:
        if not self.up:
            raise LLMUnavailable("fake llm down")
        self.calls.append((role, user))
        queue = self.json_responses.get(role)
        if queue:
            return queue.pop(0) if len(queue) > 1 else queue[0]
        return {}

    async def chat_text(self, role: str, system: str, user: str) -> str:
        if not self.up:
            raise LLMUnavailable("fake llm down")
        self.calls.append((role, user))
        return self.text_response

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not self.up:
            raise LLMUnavailable("fake llm down")
        # Deterministic 64-dim hash embedding: stable across runs, good enough
        # to test the vector plumbing without a model.
        out = []
        for t in texts:
            h = abs(hash(t))
            out.append([((h >> i) % 97) / 97.0 for i in range(64)])
        return out
