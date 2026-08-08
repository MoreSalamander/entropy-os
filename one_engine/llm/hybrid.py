"""Chat from one provider, embeddings from another.

This exists because the two capabilities do not move together. Anthropic
publishes no embeddings endpoint, but every engine hands its LLM client to a
`VectorIndex` that calls `embed()` for semantic entity resolution. So "run this
on Claude" has to mean "chat on Claude, embeddings somewhere else" — and the
somewhere else is normally the local `nomic-embed-text` that is already there,
costs nothing, and never needed to move to the cloud in the first place.

Composing two clients states that arrangement plainly instead of hiding it
inside one class that is secretly two backends.
"""

from __future__ import annotations

from typing import Any

import httpx

from .claude import LLMUnavailable
from .spec import LLMSpec


class OllamaEmbedder:
    """Just the embeddings half of Ollama.

    Written against Ollama's HTTP API directly rather than reusing the engines'
    `OllamaClient`, so that one-engine stays importable and testable in its own
    environment — this module must not require an engine venv to load.
    """

    def __init__(self, base_url: str, model: str, timeout_s: float = 120.0):
        self.model = model
        self._client = httpx.AsyncClient(base_url=base_url,
                                         timeout=httpx.Timeout(timeout_s))

    async def available(self) -> bool:
        try:
            r = await self._client.get("/api/tags")
            r.raise_for_status()
            return True
        except Exception:      # noqa: BLE001 — any failure means "not usable"
            return False

    async def embed(self, texts: list[str]) -> list[list[float]]:
        try:
            r = await self._client.post("/api/embed",
                                        json={"model": self.model, "input": texts})
            r.raise_for_status()
            return r.json()["embeddings"]
        except (httpx.HTTPError, KeyError) as e:
            raise LLMUnavailable(f"embed failed: {e}") from e

    async def aclose(self) -> None:
        await self._client.aclose()


class HybridClient:
    """One `LLMClient` assembled from a chat backend and an embed backend."""

    def __init__(self, chat: Any, embedder: Any | None):
        self._chat = chat
        self._embedder = embedder

    async def available(self) -> bool:
        # Chat availability is the answer: embeddings are optional by design,
        # and the engines already run degraded without them. Reporting "down"
        # because a local embedder is missing would refuse work that can
        # actually be done.
        return await self._chat.available()

    async def chat_json(self, role: str, system: str, user: str,
                        schema: dict[str, Any]) -> dict[str, Any]:
        return await self._chat.chat_json(role, system, user, schema)

    async def chat_text(self, role: str, system: str, user: str) -> str:
        return await self._chat.chat_text(role, system, user)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if self._embedder is None:
            raise LLMUnavailable(
                "embeddings are disabled for this run; entity resolution "
                "falls back to exact match")
        return await self._embedder.embed(texts)

    async def aclose(self) -> None:
        for part in (self._chat, self._embedder):
            if part is not None and hasattr(part, "aclose"):
                await part.aclose()


def build_hybrid(spec: LLMSpec) -> HybridClient:
    """A Claude chat client paired with local embeddings, per the spec."""
    from .claude import ClaudeClient

    embedder = None
    if spec.embed_base_url and spec.embed_model:
        embedder = OllamaEmbedder(spec.embed_base_url, spec.embed_model)
    return HybridClient(ClaudeClient(spec), embedder)
