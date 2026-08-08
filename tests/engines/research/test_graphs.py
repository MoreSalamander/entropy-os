"""Context Graph and Knowledge Graph behavior."""

from __future__ import annotations

import json

from entropy_os.engines.research.graphs.context_graph import ContextGraph
from entropy_os.engines.research.graphs.knowledge_graph import KnowledgeGraph
from entropy_os.engines.research.graphs.store import NetworkXJSONStore
from entropy_os.engines.research.graphs.vector_index import VectorIndex
from entropy_os.engines.research.llm.client import FakeLLM
from entropy_os.engines.research.models import (Entity, EntityType, ExtractionResult,
                                    Polarity, Predicate, Relationship)

from .conftest import make_claim, make_evidence


def _extraction(entities, claims=(), rels=()):
    return ExtractionResult(doc_url="https://x/doc", entities=list(entities),
                            claims=list(claims), relationships=list(rels))


class TestContextGraph:
    def test_within_session_entity_resolution(self, plan):
        cg = ContextGraph("s1", plan)
        e1 = Entity(name="Quantum Computing", description="short")
        e2 = Entity(name="quantum-computing!", description="a much longer description wins")
        cg.add_extraction("Agent", _extraction([e1]))
        cg.add_extraction("Agent", _extraction([e2]))
        assert len(cg.entities) == 1
        merged = next(iter(cg.entities.values()))
        assert "longer" in merged.description  # richer description kept

    def test_contradiction_candidates_pair_opposite_polarity(self, plan, entities):
        cg = ContextGraph("s1", plan)
        qc = entities["qc"]
        c1 = make_claim("QC will scale", [qc.id], [make_evidence()])
        c2 = make_claim("QC cannot scale", [qc.id], [make_evidence(source="hackernews")],
                        polarity=Polarity.DISPUTES)
        cg.add_extraction("A", _extraction([qc], [c1]))
        cg.add_extraction("B", _extraction([qc], [c2]))
        assert len(cg.contradiction_candidates) == 1

    def test_confidence_rewards_independent_sources(self, plan, entities):
        cg = ContextGraph("s1", plan)
        qc = entities["qc"]
        one_source = make_claim("x", [qc.id], [make_evidence(reliability=0.6)])
        cg.add_extraction("A", _extraction([qc], [one_source]))
        base = cg.entity_confidence(qc.id)
        multi = make_claim("y", [qc.id], [make_evidence(source="pubmed", reliability=0.6)])
        cg.add_extraction("B", _extraction([qc], [multi]))
        assert cg.entity_confidence(qc.id) > base  # corroboration bonus applied

    def test_atomic_save_snapshot(self, plan, entities, tmp_path):
        cg = ContextGraph("s1", plan)
        qc = entities["qc"]
        cg.add_extraction("A", _extraction([qc], [make_claim("x", [qc.id], [make_evidence()])]))
        path = cg.save(tmp_path)
        data = json.loads(path.read_text())
        assert data["topic"] == plan.topic
        assert len(data["entities"]) == 1
        assert len(data["claims"]) == 1
        assert not list(tmp_path.glob("*.tmp"))  # atomic replace left no debris


def _kg(tmp_path, llm=None):
    llm = llm or FakeLLM()
    store = NetworkXJSONStore(tmp_path / "kg.json")
    vectors = VectorIndex(llm, path=tmp_path / "qdrant")
    return KnowledgeGraph(store, vectors, llm)


class TestKnowledgeGraph:
    async def test_exact_and_alias_resolution(self, tmp_path):
        kg = _kg(tmp_path)
        e = Entity(name="IBM", type=EntityType.COMPANY, description="tech company")
        id1 = await kg.resolve(e, "s1")
        id2 = await kg.resolve(Entity(name="ibm!", description="dup"), "s2")
        assert id1 == id2
        props = kg.store.get_node(id1)
        assert set(props["sessions"]) == {"s1", "s2"}  # historical tracking

    async def test_judge_confirmed_merge_records_alias(self, tmp_path):
        llm = FakeLLM({"judge": [{"same_entity": True, "reason": "same org"}]})
        kg = _kg(tmp_path, llm)
        id1 = await kg.resolve(Entity(name="International Business Machines",
                                      description="the tech giant"), "s1")
        # different name, no alias hit → forced through the similarity rung
        async def fake_similar(name, desc, thr, limit=3):
            return [(id1, 0.95)]
        kg.vectors.similar = fake_similar
        id2 = await kg.resolve(Entity(name="IBM Corp", description="the tech giant"), "s2")
        assert id2 == id1
        assert "IBM Corp" in kg.store.get_node(id1)["aliases"]
        # alias now resolves deterministically (rung 1) in later sessions
        id3 = await kg.resolve(Entity(name="ibm corp", description=""), "s3")
        assert id3 == id1

    async def test_judge_rejection_creates_new_node(self, tmp_path):
        llm = FakeLLM({"judge": [{"same_entity": False, "reason": "different things"}]})
        kg = _kg(tmp_path, llm)
        id1 = await kg.resolve(Entity(name="GPT-4", description="model"), "s1")
        async def fake_similar(name, desc, thr, limit=3):
            return [(id1, 0.9)]
        kg.vectors.similar = fake_similar
        id2 = await kg.resolve(Entity(name="GPT-4o", description="different model"), "s1")
        assert id2 != id1  # judge said no → no merge, fail-closed

    async def test_relationship_idempotent_upsert(self, tmp_path):
        kg = _kg(tmp_path)
        a = await kg.resolve(Entity(name="A"), "s1")
        b = await kg.resolve(Entity(name="B"), "s1")
        rel = Relationship(subject_id="x", predicate=Predicate.USES, object_id="y",
                          evidence_ids=["e1"], confidence=0.5)
        kg.add_relationship(rel, a, b, "s1")
        rel2 = Relationship(subject_id="x", predicate=Predicate.USES, object_id="y",
                           evidence_ids=["e2"], confidence=0.8)
        kg.add_relationship(rel2, a, b, "s2")
        edges = [e for e in kg.store.edges_of(a) if e[0] == a and e[2] == "uses"]
        assert len(edges) == 1                      # no duplicate edge
        props = edges[0][3]
        assert props["evidence_count"] == 2         # history accumulated
        assert props["confidence"] == 0.8           # strongest wins
        assert set(props["sessions"]) == {"s1", "s2"}

    async def test_absorb_promotes_only_verified(self, plan, tmp_path, entities):
        kg = _kg(tmp_path)
        cg = ContextGraph("s9", plan)
        qc, ibm = entities["qc"], entities["ibm"]
        good = make_claim("verified fact", [qc.id], [make_evidence(reliability=0.9)])
        bad = make_claim("rumor", [ibm.id], [make_evidence(source="reddit", reliability=0.2)])
        rel = Relationship(subject_id=qc.id, predicate=Predicate.USES,
                          object_id=ibm.id, confidence=0.5)
        cg.add_extraction("A", _extraction([qc, ibm], [good, bad], [rel]))
        good_id = next(cid for cid, c in cg.claims.items() if c.statement == "verified fact")
        cg.claims[good_id].verified = True

        result = await kg.absorb(cg, {good_id})
        assert result["entities_promoted"] == 1      # only the verified claim's entity
        assert result["relationships_promoted"] == 0 # rel endpoint (ibm) not promoted
        assert kg.find_by_name("Quantum Computing") is not None
        assert kg.find_by_name("IBM") is None        # unverified stays out of the KG

    async def test_known_entities_for_feeds_planner(self, tmp_path):
        kg = _kg(tmp_path)
        await kg.resolve(Entity(name="Superconducting Qubits",
                                description="quantum hardware approach"), "s1")
        hits = kg.known_entities_for("quantum computing hardware")
        assert "Superconducting Qubits" in hits

    async def test_cross_domain_paths_between_names(self, tmp_path):
        kg = _kg(tmp_path)
        a = await kg.resolve(Entity(name="AI Research"), "s1")
        b = await kg.resolve(Entity(name="Semiconductors"), "s1")
        c = await kg.resolve(Entity(name="Energy Systems"), "s1")
        r1 = Relationship(subject_id="x", predicate=Predicate.DEPENDS_ON, object_id="y")
        kg.add_relationship(r1, a, b, "s1")
        r2 = Relationship(subject_id="x", predicate=Predicate.RELATED_TO, object_id="y")
        kg.add_relationship(r2, b, c, "s1")
        paths = kg.paths_between_names("AI Research", "Energy Systems")
        assert ["AI Research", "Semiconductors", "Energy Systems"] in paths


class TestVectorIndex:
    async def test_identical_text_is_top_hit(self, tmp_path):
        vi = VectorIndex(FakeLLM(), path=tmp_path / "q")
        await vi.upsert_entity("e1", "Transformer", "attention architecture")
        await vi.upsert_entity("e2", "Banana", "a fruit")
        hits = await vi.similar("Transformer", "attention architecture", threshold=0.99)
        assert hits and hits[0][0] == "e1"
        vi.close()

    async def test_embed_down_degrades_not_crashes(self, tmp_path):
        vi = VectorIndex(FakeLLM(up=False), path=tmp_path / "q")
        await vi.upsert_entity("e1", "X", "y")   # silently skipped
        assert await vi.similar("X", "y", 0.5) == []
        assert vi.degraded is True
        vi.close()
