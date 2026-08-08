"""Knowledge Graph — persistent intelligence across ALL research sessions.

What it adds over the Context Graph:
  * entity resolution across sessions — three rungs, cheapest first:
      1. exact normalized-name / alias match          (deterministic)
      2. embedding similarity above threshold         (proposes)
      3. judge-model confirmation of the merge        (decides; different
         model family than the extractor, per judge-separation)
    A merge that the judge rejects becomes a new node. Aliases accumulate.
  * historical tracking — first_seen / last_seen / session list per node
    and per edge, so "what changed recently" is queryable, not vibes
  * relationship discovery & cross-domain reasoning — paths_between and
    neighborhood over the whole accumulated graph
  * the avoid-relearning surface — known_entities_for() feeds the planner

Storage is a GraphStore (embedded JSON default, Neo4j via config flip).
"""

from __future__ import annotations

from ..llm.client import LLMClient, LLMUnavailable
from ..models import Entity, Relationship, normalize_name, now_utc
from .context_graph import ContextGraph
from .store import GraphStore
from .vector_index import VectorIndex

_JUDGE_SCHEMA = {
    "type": "object",
    "properties": {"same_entity": {"type": "boolean"},
                   "reason": {"type": "string"}},
    "required": ["same_entity", "reason"],
}

_JUDGE_SYSTEM = """You judge whether two entity records refer to the SAME real-world thing.
Answer same_entity=true only when they clearly do (e.g. "GPT-4" and "OpenAI GPT-4").
Different versions, products, or organizations are NOT the same entity."""


class KnowledgeGraph:
    def __init__(self, store: GraphStore, vectors: VectorIndex, llm: LLMClient,
                 merge_threshold: float = 0.86):
        self.store = store
        self.vectors = vectors
        self.llm = llm
        self.merge_threshold = merge_threshold
        # name/alias -> node id map, rebuilt from the store at startup
        self._by_norm: dict[str, str] = {}
        for node_id, props in self.store.all_nodes():
            if props.get("kind") != "entity":
                continue
            self._by_norm[normalize_name(props.get("name", ""))] = node_id
            for alias in props.get("aliases", []) or []:
                self._by_norm.setdefault(normalize_name(alias), node_id)

    # ------------------------------------------------------------------ #
    # entity resolution
    # ------------------------------------------------------------------ #
    async def resolve(self, ent: Entity, session_id: str) -> str:
        """Return the KG node id for this entity, merging when justified."""
        # Rung 1: deterministic name/alias hit
        node_id = self._by_norm.get(ent.norm_name)
        if node_id:
            self._touch(node_id, ent, session_id)
            return node_id

        # Rung 2: embedding similarity proposes candidates
        candidates = await self.vectors.similar(
            ent.name, ent.description, self.merge_threshold)
        for cand_id, _score in candidates:
            props = self.store.get_node(cand_id)
            if not props:
                continue
            # Rung 3: judge decides (LLM proposes nothing here — it only
            # answers a yes/no the deterministic layer acts on)
            if await self._judge_same(ent, props):
                self._touch(cand_id, ent, session_id, alias=ent.name)
                return cand_id

        # New knowledge: create the node
        node_id = ent.id
        self.store.upsert_node(node_id, {
            "kind": "entity", "name": ent.name, "type": ent.type.value,
            "description": ent.description, "aliases": ent.aliases,
            "domains": ent.domains,
            "first_seen": now_utc().isoformat(),
            "last_seen": now_utc().isoformat(),
            "sessions": [session_id],
        })
        self._by_norm[ent.norm_name] = node_id
        await self.vectors.upsert_entity(node_id, ent.name, ent.description)
        return node_id

    async def _judge_same(self, ent: Entity, props: dict) -> bool:
        try:
            verdict = await self.llm.chat_json(
                "judge", _JUDGE_SYSTEM,
                f"Record A: {ent.name} — {ent.description[:200]}\n"
                f"Record B: {props.get('name')} — {str(props.get('description'))[:200]}",
                _JUDGE_SCHEMA)
            return bool(verdict.get("same_entity") is True)
        except LLMUnavailable:
            return False  # fail-closed: no judge, no merge

    def _touch(self, node_id: str, ent: Entity, session_id: str,
               alias: str | None = None) -> None:
        """Historical tracking update on an existing node."""
        props = self.store.get_node(node_id) or {}
        sessions = list(props.get("sessions", []))
        if session_id not in sessions:
            sessions.append(session_id)
        aliases = list(props.get("aliases", []))
        if alias and alias not in aliases and normalize_name(alias) != normalize_name(props.get("name", "")):
            aliases.append(alias)
            self._by_norm[normalize_name(alias)] = node_id
        update = {"last_seen": now_utc().isoformat(), "sessions": sessions,
                  "aliases": aliases}
        if ent.description and len(ent.description) > len(str(props.get("description", ""))):
            update["description"] = ent.description
        self.store.upsert_node(node_id, update)

    # ------------------------------------------------------------------ #
    # relationships
    # ------------------------------------------------------------------ #
    def add_relationship(self, rel: Relationship, subj_kg: str, obj_kg: str,
                         session_id: str) -> None:
        """Idempotent edge upsert keyed by (subject, predicate, object) so the
        same fact re-learned later strengthens history instead of duplicating."""
        key = f"{rel.predicate.value}"
        existing = [e for e in self.store.edges_of(subj_kg)
                    if e[0] == subj_kg and e[1] == obj_kg and e[2] == key]
        if existing:
            props = existing[0][3]
            sessions = list(props.get("sessions", []))
            if session_id not in sessions:
                sessions.append(session_id)
            self.store.upsert_edge(subj_kg, obj_kg, key, {
                "last_seen": now_utc().isoformat(), "sessions": sessions,
                "evidence_count": int(props.get("evidence_count", 0)) + len(rel.evidence_ids),
                "confidence": max(float(props.get("confidence", 0.0)), rel.confidence),
            })
        else:
            self.store.upsert_edge(subj_kg, obj_kg, key, {
                "predicate": rel.predicate.value,
                "confidence": rel.confidence,
                "evidence_count": len(rel.evidence_ids),
                "first_seen": now_utc().isoformat(),
                "last_seen": now_utc().isoformat(),
                "sessions": [session_id],
            })

    # ------------------------------------------------------------------ #
    # query surface (planner, agents, API)
    # ------------------------------------------------------------------ #
    def known_entities_for(self, topic: str, limit: int = 30) -> list[str]:
        """Avoid-relearning hook: entity names the KG already holds whose
        name/description overlaps the topic terms."""
        terms = {t for t in normalize_name(topic).split() if len(t) > 3}
        if not terms:
            return []
        hits: list[tuple[int, str]] = []
        for _nid, props in self.store.all_nodes():
            if props.get("kind") != "entity":
                continue
            hay = normalize_name(f"{props.get('name', '')} {props.get('description', '')}")
            overlap = sum(1 for t in terms if t in hay)
            if overlap:
                hits.append((overlap, props.get("name", "")))
        return [name for _n, name in sorted(hits, reverse=True)[:limit]]

    def find_by_name(self, name: str) -> str | None:
        return self._by_norm.get(normalize_name(name))

    def paths_between_names(self, a: str, b: str, cutoff: int = 4) -> list[list[str]]:
        """Cross-domain reasoning: named-entity paths through the whole KG."""
        ida, idb = self.find_by_name(a), self.find_by_name(b)
        if not ida or not idb:
            return []
        paths = self.store.paths_between(ida, idb, cutoff)
        out = []
        for p in paths:
            names = []
            for nid in p:
                props = self.store.get_node(nid) or {}
                names.append(props.get("name", nid))
            out.append(names)
        return out

    def stats(self) -> dict:
        nodes = self.store.all_nodes()
        edges = self.store.all_edges()
        return {
            "entities": sum(1 for _n, p in nodes if p.get("kind") == "entity"),
            "relationships": len(edges),
            "sessions_seen": len({s for _n, p in nodes
                                  for s in p.get("sessions", [])}),
        }

    # ------------------------------------------------------------------ #
    # consolidation entry point (called by learning/consolidator.py)
    # ------------------------------------------------------------------ #
    async def absorb(self, cg: ContextGraph, verified_claim_ids: set[str]) -> dict:
        """Promote the VERIFIED part of a session's Context Graph into the KG.
        Only entities touched by verified claims and relationships whose
        endpoints made it in are absorbed — the verification gate is what
        separates session context from persistent knowledge."""
        promoted_entities: dict[str, str] = {}  # cg id -> kg id
        keep_entities: set[str] = set()
        for cid in verified_claim_ids:
            claim = cg.claims.get(cid)
            if claim:
                keep_entities.update(claim.entity_ids)

        for eid in keep_entities:
            ent = cg.entities.get(eid)
            if ent:
                promoted_entities[eid] = await self.resolve(ent, cg.session_id)

        promoted_rels = 0
        for rel in cg.relationships.values():
            subj_kg = promoted_entities.get(rel.subject_id)
            obj_kg = promoted_entities.get(rel.object_id)
            if subj_kg and obj_kg and subj_kg != obj_kg:
                self.add_relationship(rel, subj_kg, obj_kg, cg.session_id)
                promoted_rels += 1

        self.store.flush()
        return {"entities_promoted": len(promoted_entities),
                "relationships_promoted": promoted_rels}
