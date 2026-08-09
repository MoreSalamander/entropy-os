"""Continuous Learning System — the spec's workflow, literally:

    New Research → Extract Knowledge → Validate → Update Knowledge Graph
                → Improve Future Research

Each arrow is a concrete mechanism, not a slogan:
  Validate                the VerificationAgent's claim gate ran first; only
                          verified claim ids reach this module
  Update Knowledge Graph  KnowledgeGraph.absorb() promotes the verified
                          subgraph with cross-session entity resolution
  Improve Future Research three surfaces —
                            1. ledger doc-hash index: known docs are never
                               re-extracted in any later session
                            2. KG known_entities_for(): the next plan for a
                               related topic starts from what is known
                            3. QuestionAgent findings persist on the session
                               file as ready-made follow-up research paths
"""

from __future__ import annotations

from pathlib import Path

from ..graphs.context_graph import ContextGraph
from ..graphs.knowledge_graph import KnowledgeGraph
from ..models import Finding


class Consolidator:
    def __init__(self, kg: KnowledgeGraph, sessions_dir: Path):
        self.kg = kg
        self.sessions_dir = sessions_dir

    async def consolidate(self, cg: ContextGraph,
                          findings: list[Finding]) -> dict:
        verified_ids = {cid for cid, c in cg.claims.items() if c.verified}
        promo = await self.kg.absorb(cg, verified_ids)

        # follow-up paths ride on the session snapshot for the next run
        cg.open_questions = [f.text for f in findings if f.kind == "question"]
        session_path = cg.save(self.sessions_dir)

        return {
            **promo,
            "claims_verified": len(verified_ids),
            "claims_total": len(cg.claims),
            "session_file": str(session_path),
            "kg_after": self.kg.stats(),
        }
