"""Vector index for semantic entity resolution — Qdrant in embedded mode.

qdrant-client's local mode (path=...) is a full Qdrant implementation with
zero servers; setting vectors.url in config flips the same code to a real
Qdrant server. Embeddings come from Ollama (nomic-embed-text). If the embed
model is unreachable the index reports itself degraded and the KG falls back
to name-only resolution — honestly weaker, never silently wrong.
"""

from __future__ import annotations

from pathlib import Path

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from ..llm.client import LLMClient, LLMUnavailable

_COLLECTION = "kg_entities"


class VectorIndex:
    def __init__(self, llm: LLMClient, path: Path | None = None, url: str = ""):
        self.llm = llm
        self.degraded = False
        self.client = QdrantClient(url=url) if url else QdrantClient(path=str(path))
        self._dim: int | None = None
        self._id_seq = 0
        self._pid_to_entity: dict[int, str] = {}
        self._entity_to_pid: dict[str, int] = {}
        self._restore_maps()

    def _restore_maps(self) -> None:
        """Rebuild the point-id ↔ entity-id maps from a persisted collection."""
        try:
            if not self.client.collection_exists(_COLLECTION):
                return
            offset = None
            while True:
                points, offset = self.client.scroll(
                    _COLLECTION, limit=256, offset=offset, with_payload=True)
                for p in points:
                    eid = (p.payload or {}).get("entity_id")
                    if eid:
                        pid = int(p.id)
                        self._pid_to_entity[pid] = eid
                        self._entity_to_pid[eid] = pid
                        self._id_seq = max(self._id_seq, pid + 1)
                if offset is None:
                    break
        except Exception:  # noqa: BLE001 — a broken index degrades, never crashes
            self.degraded = True

    async def _embed_one(self, text: str) -> list[float] | None:
        try:
            vecs = await self.llm.embed([text[:1000]])
            return vecs[0] if vecs else None
        except LLMUnavailable:
            self.degraded = True
            return None

    def _ensure_collection(self, dim: int) -> None:
        if self._dim is not None:
            return
        self._dim = dim
        if not self.client.collection_exists(_COLLECTION):
            self.client.create_collection(
                _COLLECTION,
                vectors_config=VectorParams(size=dim, distance=Distance.COSINE))

    async def upsert_entity(self, entity_id: str, name: str, description: str) -> None:
        vec = await self._embed_one(f"{name}. {description}")
        if vec is None:
            return
        self._ensure_collection(len(vec))
        pid = self._entity_to_pid.get(entity_id)
        if pid is None:
            pid = self._id_seq
            self._id_seq += 1
            self._pid_to_entity[pid] = entity_id
            self._entity_to_pid[entity_id] = pid
        self.client.upsert(_COLLECTION, points=[
            PointStruct(id=pid, vector=vec, payload={"entity_id": entity_id, "name": name})])

    async def similar(self, name: str, description: str,
                      threshold: float, limit: int = 3) -> list[tuple[str, float]]:
        """Return [(entity_id, score)] above threshold — merge CANDIDATES only;
        the judge model confirms before any merge happens."""
        if self._dim is None and not self.client.collection_exists(_COLLECTION):
            return []
        vec = await self._embed_one(f"{name}. {description}")
        if vec is None:
            return []
        self._ensure_collection(len(vec))
        hits = self.client.query_points(_COLLECTION, query=vec, limit=limit).points
        return [((h.payload or {}).get("entity_id", ""), h.score)
                for h in hits if h.score >= threshold and (h.payload or {}).get("entity_id")]

    def close(self) -> None:
        self.client.close()
