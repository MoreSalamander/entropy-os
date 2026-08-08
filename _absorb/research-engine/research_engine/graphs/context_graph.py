"""Context Graph — situational awareness for ONE research session.

Tracks, live, while workers stream evidence in:
  * active entities (merged within-session by normalized name)
  * current claims + their evidence
  * research branches (which agent/source produced what)
  * contradiction CANDIDATES (deterministic pairing; the Contradiction agent
    confirms or clears them)
  * per-entity confidence rollups
  * open questions

It is a networkx MultiDiGraph because a session graph must be cheap to
mutate thousands of times; persistence is a JSON snapshot per session.
The graph evolves DURING the run — add_extraction() is called from the
orchestrator as each document finishes, not in a batch at the end.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import networkx as nx

from ..models import (Claim, Entity, ExtractionResult, Polarity, Relationship,
                      ResearchPlan, new_id, normalize_name, now_utc)


class ContextGraph:
    def __init__(self, session_id: str, plan: ResearchPlan):
        self.session_id = session_id
        self.plan = plan
        self.g = nx.MultiDiGraph()
        self.entities: dict[str, Entity] = {}          # id -> Entity
        self._by_norm: dict[str, str] = {}             # normalized name -> id
        self.claims: dict[str, Claim] = {}             # id -> Claim
        self.relationships: dict[str, Relationship] = {}
        self.branches: dict[str, list[str]] = defaultdict(list)  # agent -> doc urls
        self.claim_branch: dict[str, str] = {}         # claim id -> producing agent
        self.open_questions: list[str] = list(plan.research_questions)
        self.contradiction_candidates: list[tuple[str, str]] = []  # (claim_id, claim_id)
        self.g.add_node("topic", kind="topic", label=plan.topic)

    # ------------------------------------------------------------------ #
    # ingestion (called live by the orchestrator)
    # ------------------------------------------------------------------ #
    def resolve_entity(self, ent: Entity) -> str:
        """Within-session resolution: same normalized name = same node.
        Cross-session resolution (embeddings + judge) happens in the KG."""
        key = ent.norm_name
        existing_id = self._by_norm.get(key)
        if existing_id:
            existing = self.entities[existing_id]
            existing.last_seen = now_utc()
            if ent.description and len(ent.description) > len(existing.description):
                existing.description = ent.description  # keep the richer description
            return existing_id
        self.entities[ent.id] = ent
        self._by_norm[key] = ent.id
        self.g.add_node(ent.id, kind="entity", label=ent.name, type=ent.type.value)
        self.g.add_edge("topic", ent.id, key="mentions", kind="mentions")
        return ent.id

    def add_extraction(self, agent: str, result: ExtractionResult) -> None:
        """Stream one document's validated extraction into the session graph."""
        self.branches[agent].append(result.doc_url)
        id_map: dict[str, str] = {}  # extraction-local id -> session id
        for ent in result.entities:
            id_map[ent.id] = self.resolve_entity(ent)

        for claim in result.claims:
            claim.entity_ids = [id_map.get(i, i) for i in claim.entity_ids]
            self.claims[claim.id] = claim
            self.claim_branch[claim.id] = agent
            self.g.add_node(claim.id, kind="claim", label=claim.statement[:80])
            for eid in claim.entity_ids:
                self.g.add_edge(claim.id, eid, key=claim.id, kind="about")
            self._register_contradiction_candidates(claim)

        for rel in result.relationships:
            rel.subject_id = id_map.get(rel.subject_id, rel.subject_id)
            rel.object_id = id_map.get(rel.object_id, rel.object_id)
            if rel.subject_id == rel.object_id:
                continue  # resolution may have merged endpoints; drop self-loops
            rel.sessions = [self.session_id]
            self.relationships[rel.id] = rel
            self.g.add_edge(rel.subject_id, rel.object_id,
                            key=rel.id, kind=rel.predicate.value)

    def _register_contradiction_candidates(self, new_claim: Claim) -> None:
        """Deterministic candidate generation: two claims sharing an entity with
        opposite polarity are a candidate pair. The Contradiction agent later
        judges whether they actually oppose each other semantically."""
        new_entities = set(new_claim.entity_ids)
        for other in self.claims.values():
            if other.id == new_claim.id:
                continue
            if (other.polarity != new_claim.polarity
                    and new_entities & set(other.entity_ids)):
                self.contradiction_candidates.append((other.id, new_claim.id))

    # ------------------------------------------------------------------ #
    # rollups the reasoning layer and report read
    # ------------------------------------------------------------------ #
    def entity_confidence(self, entity_id: str) -> float:
        """Corroboration-weighted confidence: mean evidence reliability boosted
        by the number of INDEPENDENT sources touching the entity."""
        evs = [ev for c in self.claims.values() if entity_id in c.entity_ids
               for ev in c.evidence]
        if not evs:
            return 0.0
        mean_rel = sum(e.reliability for e in evs) / len(evs)
        distinct_sources = len({e.source for e in evs})
        corroboration = min(0.2, 0.05 * (distinct_sources - 1))
        return round(min(0.99, mean_rel + corroboration), 3)

    def evidence_by_id(self) -> dict[str, object]:
        return {ev.id: ev for c in self.claims.values() for ev in c.evidence}

    def top_entities(self, n: int = 15) -> list[tuple[Entity, float, int]]:
        """(entity, confidence, mention_count) sorted by weight — feeds the report."""
        counts: dict[str, int] = defaultdict(int)
        for c in self.claims.values():
            for eid in c.entity_ids:
                counts[eid] += 1
        rows = [(self.entities[eid], self.entity_confidence(eid), n_mentions)
                for eid, n_mentions in counts.items() if eid in self.entities]
        return sorted(rows, key=lambda r: (r[2], r[1]), reverse=True)[:n]

    # ------------------------------------------------------------------ #
    # persistence
    # ------------------------------------------------------------------ #
    def snapshot(self) -> dict:
        return {
            "session_id": self.session_id,
            "topic": self.plan.topic,
            "generated_at": now_utc().isoformat(),
            "plan": json.loads(self.plan.model_dump_json()),
            "entities": [json.loads(e.model_dump_json()) for e in self.entities.values()],
            "claims": [json.loads(c.model_dump_json()) for c in self.claims.values()],
            "relationships": [json.loads(r.model_dump_json())
                              for r in self.relationships.values()],
            "branches": dict(self.branches),
            "open_questions": self.open_questions,
            "contradiction_candidates": self.contradiction_candidates,
        }

    def save(self, sessions_dir: Path) -> Path:
        sessions_dir.mkdir(parents=True, exist_ok=True)
        path = sessions_dir / f"{self.session_id}.json"
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self.snapshot(), indent=2, default=str))
        tmp.replace(path)  # atomic write: a crash never leaves a torn session file
        return path


def new_session_id() -> str:
    return new_id("session")
