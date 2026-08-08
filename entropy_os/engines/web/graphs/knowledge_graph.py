"""Phase 4 + 8 — Design Knowledge Graph: persistent design intelligence.

Built on research-engine's GraphStore + VectorIndex primitives (engine on
engine). Node kinds: website, industry, trait, section, technology, project.
Edge vocabulary: exhibits, common_in, used_by, scored — the
industry↔design-decision relationships the spec asks the system to learn.

Semantic search (the Phase 2 promise, honest mechanism): every analyzed
website gets an embedded "design fingerprint" (its abstract traits +
description). `semantic_match(traits)` embeds the INTENT's psychology axes
and returns the corpus sites that best communicate them — search by intent
over everything the engine has ever analyzed.

The memory loop (Phase 8): record_outcome() stores each generated site's
design choices and review scores; `priors_for(industry)` returns
section/palette/font weights biased by (a) what the analyzed corpus of that
industry exhibits and (b) which of OUR OWN past choices scored well. No
fabricated conversion data — human feedback joins via record_feedback().
"""

from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path

from entropy_os.engines.research.graphs.store import GraphStore
from entropy_os.engines.research.graphs.vector_index import VectorIndex
from entropy_os.engines.research.models import normalize_name, now_utc

from ..models import ProjectOutcome, SiteAnalysis


class DesignKnowledgeGraph:
    def __init__(self, store: GraphStore, vectors: VectorIndex):
        self.store = store
        self.vectors = vectors

    # ------------------------------------------------------------------ #
    # absorption (called by the engine after research + after generation)
    # ------------------------------------------------------------------ #
    async def absorb_analysis(self, analysis: SiteAnalysis, industry: str) -> None:
        if not analysis.ok:
            return
        site_id = f"website:{normalize_name(analysis.url)}"
        existing = self.store.get_node(site_id) or {}
        self.store.upsert_node(site_id, {
            "kind": "website", "url": analysis.url,
            "name": analysis.title[:120] or analysis.url,
            "category": analysis.seed_category,
            "first_seen": existing.get("first_seen", now_utc().isoformat()),
            "last_seen": now_utc().isoformat(),
            "times_analyzed": int(existing.get("times_analyzed", 0)) + 1,
        })
        ind_id = f"industry:{normalize_name(industry)}"
        self.store.upsert_node(ind_id, {"kind": "industry", "name": industry})
        self.store.upsert_edge(site_id, ind_id, "relevant_to",
                               {"last_seen": now_utc().isoformat()})
        trait_names: list[str] = []
        for trait in analysis.traits:
            t_id = f"trait:{trait.kind.value}:{trait.name}"
            self.store.upsert_node(t_id, {"kind": "trait",
                                          "trait_kind": trait.kind.value,
                                          "name": trait.name})
            self.store.upsert_edge(site_id, t_id, "exhibits", {"value": trait.value})
            # the industry↔design-decision learning edge, count-weighted
            edge = [e for e in self.store.edges_of(ind_id)
                    if e[0] == t_id and e[1] == ind_id and e[2] == "common_in"]
            count = int(edge[0][3].get("count", 0)) + 1 if edge else 1
            self.store.upsert_edge(t_id, ind_id, "common_in", {"count": count})
            trait_names.append(trait.name)
        # design fingerprint for semantic matching
        fingerprint = (f"{analysis.title}. {analysis.description} "
                       f"design traits: {', '.join(trait_names)}")
        await self.vectors.upsert_entity(site_id, analysis.title or analysis.url,
                                         fingerprint[:900])

    # ------------------------------------------------------------------ #
    # semantic search over the accumulated corpus
    # ------------------------------------------------------------------ #
    async def semantic_match(self, semantic_traits: list[str],
                             limit: int = 8) -> list[tuple[str, float]]:
        """[(website node id, score)] for sites whose design fingerprint best
        matches the intent axes. Threshold is low on purpose — ranking, not
        gating; an empty corpus returns an empty list, never an error."""
        query = "a website that communicates: " + ", ".join(semantic_traits)
        return await self.vectors.similar(query, "", threshold=0.3, limit=limit)

    # ------------------------------------------------------------------ #
    # Phase 8 memory loop
    # ------------------------------------------------------------------ #
    def record_outcome(self, outcome: ProjectOutcome) -> None:
        pid = f"project:{outcome.project_id}"
        self.store.upsert_node(pid, {
            "kind": "project", "name": outcome.project_id,
            "industry": outcome.industry,
            "review_scores": outcome.review_scores,
            "section_usage": outcome.section_usage,
            "palette_mode": outcome.palette_mode,
            "heading_font": outcome.heading_font,
            "motion": outcome.motion,
            "build_ok": outcome.build_ok,
            "created_at": outcome.created_at.isoformat(),
        })
        ind_id = f"industry:{normalize_name(outcome.industry)}"
        self.store.upsert_node(ind_id, {"kind": "industry", "name": outcome.industry})
        mean_score = (sum(outcome.review_scores.values()) /
                      max(len(outcome.review_scores), 1))
        self.store.upsert_edge(pid, ind_id, "generated_for",
                               {"mean_score": round(mean_score, 1)})
        self.store.flush()

    def record_feedback(self, project_id: str, feedback: dict) -> bool:
        pid = f"project:{project_id}"
        node = self.store.get_node(pid)
        if node is None:
            return False
        self.store.upsert_node(pid, {"human_feedback": feedback,
                                     "feedback_at": now_utc().isoformat()})
        self.store.flush()
        return True

    def priors_for(self, industry: str) -> dict:
        """What this industry's corpus exhibits + what our own past projects
        for it scored. Feeds synthesis as weights, never as mandates."""
        ind_id = f"industry:{normalize_name(industry)}"
        trait_counts: Counter = Counter()
        for src, _dst, key, props in self.store.edges_of(ind_id):
            if key == "common_in":
                node = self.store.get_node(src) or {}
                trait_counts[node.get("name", src)] = int(props.get("count", 1))
        past: list[dict] = []
        for _node_id, props in self.store.all_nodes():
            if props.get("kind") == "project" and \
               normalize_name(props.get("industry", "")) == normalize_name(industry):
                past.append(props)
        # section weights from our own scored history: sections used by
        # higher-scoring projects weigh more
        section_weight: dict[str, float] = defaultdict(float)
        for p in past:
            scores = p.get("review_scores") or {}
            mean = sum(scores.values()) / max(len(scores), 1)
            for section, n in (p.get("section_usage") or {}).items():
                section_weight[section] += mean * n / 100.0
        return {"trait_counts": dict(trait_counts),
                "past_projects": len(past),
                "section_weight": dict(section_weight)}

    def stats(self) -> dict:
        kinds: Counter = Counter()
        for _n, props in self.store.all_nodes():
            kinds[props.get("kind", "?")] += 1
        return {"nodes_by_kind": dict(kinds),
                "edges": len(self.store.all_edges())}


def load_design_kg(kg_path: Path, vectors: VectorIndex) -> DesignKnowledgeGraph:
    from entropy_os.engines.research.graphs.store import NetworkXJSONStore
    return DesignKnowledgeGraph(NetworkXJSONStore(kg_path), vectors)
