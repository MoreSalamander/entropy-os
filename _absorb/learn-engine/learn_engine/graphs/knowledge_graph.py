"""Phase 4 + 7 + 9 — Education Knowledge Graph: persistent connected knowledge.

Built on research-engine's GraphStore + VectorIndex. Nodes: concept,
resource, misconception, explanation_record. Edges: the EduRelation
vocabulary, plus has_resource / commonly_confuses / explained_by.

Phase 7 (graph reasoning) surfaces:
  missing_prerequisites(concept, mastered)  gaps on the requires-chain
  cross_disciplinary(mastered, goal)        paths from what the learner
                                            knows to the goal through other
                                            subjects — recommendations with
                                            the connecting chain shown
Phase 9 (continuous improvement) accumulates:
  record_explanation_outcome()  which explanation style worked (per concept,
                                across learners) — evidence, not vibes
  record_misconception()        the shared misconception library
"""

from __future__ import annotations

from research_engine.graphs.store import GraphStore
from research_engine.graphs.vector_index import VectorIndex
from research_engine.models import normalize_name, now_utc

from ..models import Concept, EduRelation, LearningResource, Roadmap


class EducationKnowledgeGraph:
    def __init__(self, store: GraphStore, vectors: VectorIndex):
        self.store = store
        self.vectors = vectors

    def _cid(self, name: str) -> str:
        return f"concept:{normalize_name(name)}"

    # ------------------------------------------------------------------ #
    # absorption
    # ------------------------------------------------------------------ #
    async def absorb_roadmap(self, roadmap: Roadmap) -> int:
        added = 0
        for c in roadmap.concepts:
            cid = self._cid(c.name)
            existing = self.store.get_node(cid) or {}
            self.store.upsert_node(cid, {
                "kind": "concept", "name": c.name,
                "subject": c.subject or roadmap.subject,
                "summary": c.summary or existing.get("summary", ""),
                "first_seen": existing.get("first_seen", now_utc().isoformat()),
                "last_seen": now_utc().isoformat(),
            })
            await self.vectors.upsert_entity(cid, c.name,
                                             f"{roadmap.subject}. {c.summary}")
            added += 1
        for s, rel, d in roadmap.edges:
            self.store.upsert_edge(self._cid(s), self._cid(d), rel,
                                   {"last_seen": now_utc().isoformat()})
        self.store.flush()
        return added

    def absorb_resources(self, resources: list[LearningResource]) -> int:
        for r in resources:
            rid = f"resource:{normalize_name(r.url)[:60]}"
            self.store.upsert_node(rid, {"kind": "resource", "name": r.title,
                                         "url": r.url, "res_kind": r.kind,
                                         "agent": r.agent})
            self.store.upsert_edge(self._cid(r.concept_name), rid,
                                   "has_resource", {"res_kind": r.kind})
        self.store.flush()
        return len(resources)

    # ------------------------------------------------------------------ #
    # phase 7 — graph reasoning
    # ------------------------------------------------------------------ #
    def missing_prerequisites(self, concept: str,
                              mastered: list[str]) -> list[str]:
        """Concepts on the requires-chain below `concept` not yet mastered,
        deepest first — the exact gap list the adaptive engine teaches."""
        mastered_norm = {normalize_name(m) for m in mastered}
        start = self._cid(concept)
        if self.store.get_node(start) is None:
            return []
        gaps: list[str] = []
        seen: set[str] = set()
        frontier = [start]
        while frontier:
            node = frontier.pop()
            for src, dst, kind, _props in self.store.edges_of(node):
                if src == node and kind == EduRelation.REQUIRES.value \
                        and dst not in seen:
                    seen.add(dst)
                    props = self.store.get_node(dst) or {}
                    if normalize_name(props.get("name", "")) not in mastered_norm:
                        gaps.append(props.get("name", dst))
                    frontier.append(dst)
        return list(reversed(gaps))  # deepest prerequisites first

    def cross_disciplinary(self, mastered: list[str], goal_concept: str,
                           max_paths: int = 3) -> list[list[str]]:
        """Paths from any mastered concept to the goal through the whole KG —
        the 'you know Biology, meet Neuromorphic Computing' surface."""
        goal_id = self._cid(goal_concept)
        if self.store.get_node(goal_id) is None:
            return []
        out: list[list[str]] = []
        for m in mastered:
            mid = self._cid(m)
            if self.store.get_node(mid) is None:
                continue
            for path in self.store.paths_between(mid, goal_id, cutoff=4):
                names = []
                for nid in path:
                    props = self.store.get_node(nid) or {}
                    if props.get("kind") == "concept":
                        names.append(props.get("name", nid))
                if len(names) >= 3 and names not in out:
                    out.append(names)
                if len(out) >= max_paths:
                    return out
        return out

    # ------------------------------------------------------------------ #
    # phase 9 — shared teaching memory
    # ------------------------------------------------------------------ #
    def record_explanation_outcome(self, concept: str, method: str,
                                   success: bool) -> None:
        nid = f"explanation:{normalize_name(concept)}:{method}"
        props = self.store.get_node(nid) or {
            "kind": "explanation_record", "name": f"{concept} via {method}",
            "concept": concept, "method": method, "attempts": 0, "successes": 0}
        props["attempts"] = int(props.get("attempts", 0)) + 1
        props["successes"] = int(props.get("successes", 0)) + int(success)
        self.store.upsert_node(nid, props)
        self.store.upsert_edge(self._cid(concept), nid, "explained_by", {})
        self.store.flush()

    def best_method_for(self, concept: str) -> str | None:
        best, best_rate = None, -1.0
        for _src, dst, kind, _p in self.store.edges_of(self._cid(concept)):
            if kind != "explained_by":
                continue
            props = self.store.get_node(dst) or {}
            attempts = int(props.get("attempts", 0))
            if attempts >= 2:
                rate = int(props.get("successes", 0)) / attempts
                if rate > best_rate:
                    best, best_rate = props.get("method"), rate
        return best

    def record_misconception(self, concept: str, text: str) -> None:
        nid = f"misconception:{normalize_name(text)[:60]}"
        props = self.store.get_node(nid) or {
            "kind": "misconception", "name": text[:160], "count": 0}
        props["count"] = int(props.get("count", 0)) + 1
        self.store.upsert_node(nid, props)
        self.store.upsert_edge(self._cid(concept), nid, "commonly_confuses", {})
        self.store.flush()

    def misconceptions_for(self, concept: str) -> list[str]:
        out = []
        for _src, dst, kind, _p in self.store.edges_of(self._cid(concept)):
            if kind == "commonly_confuses":
                props = self.store.get_node(dst) or {}
                out.append(props.get("name", ""))
        return [m for m in out if m]

    def resources_for(self, concept: str, kind: str | None = None,
                      limit: int = 6) -> list[dict]:
        rows = []
        for _src, dst, ekind, props in self.store.edges_of(self._cid(concept)):
            if ekind == "has_resource":
                node = self.store.get_node(dst) or {}
                if kind is None or node.get("res_kind") == kind:
                    rows.append({"title": node.get("name", ""),
                                 "url": node.get("url", ""),
                                 "kind": node.get("res_kind", ""),
                                 "agent": node.get("agent", "")})
        return rows[:limit]

    def stats(self) -> dict:
        kinds: dict[str, int] = {}
        for _n, props in self.store.all_nodes():
            kinds[props.get("kind", "?")] = kinds.get(props.get("kind", "?"), 0) + 1
        return {"nodes_by_kind": kinds, "edges": len(self.store.all_edges())}
