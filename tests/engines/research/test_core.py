"""Models, reliability scoring, and the graph store."""

from __future__ import annotations

from entropy_os.engines.research.extraction.reliability import score_reliability
from entropy_os.engines.research.graphs.store import NetworkXJSONStore
from entropy_os.engines.research.models import normalize_name

from .conftest import make_doc


class TestModels:
    def test_normalize_name(self):
        assert normalize_name("  GPT-4!  ") == normalize_name("gpt 4")
        assert normalize_name("Attention Is All You Need") == "attention is all you need"

    def test_text_hash_stable_and_distinct(self):
        a1, a2 = make_doc(url="https://x/a"), make_doc(url="https://x/a")
        b = make_doc(url="https://x/b")
        assert a1.text_hash == a2.text_hash
        assert a1.text_hash != b.text_hash


class TestReliability:
    def test_bounds(self):
        assert 0.05 <= score_reliability(make_doc(), 0.0) <= 0.99
        assert 0.05 <= score_reliability(make_doc(cited_by=10**6), 1.0) <= 0.99

    def test_recency_dampens_but_never_zeroes(self):
        fresh = score_reliability(make_doc(days_old=5), 0.8)
        stale = score_reliability(make_doc(days_old=8 * 365), 0.8)
        assert fresh > stale
        assert stale >= 0.8 * 0.7 - 1e-9  # the 0.7 recency floor holds

    def test_citations_boost(self):
        plain = score_reliability(make_doc(), 0.6)
        cited = score_reliability(make_doc(cited_by=5000), 0.6)
        assert cited > plain
        assert cited - plain <= 0.15  # capped


class TestNetworkXJSONStore:
    def test_persistence_roundtrip_and_backup(self, tmp_path):
        path = tmp_path / "kg.json"
        s1 = NetworkXJSONStore(path)
        s1.upsert_node("a", {"kind": "entity", "name": "A"})
        s1.upsert_node("b", {"kind": "entity", "name": "B"})
        s1.upsert_edge("a", "b", "uses", {"confidence": 0.7})
        s1.flush()
        s1.upsert_node("a", {"description": "updated"})
        s1.flush()  # second flush must produce a .bak of the first state

        assert list(tmp_path.glob("kg.json.bak.*")), "backup file missing"

        s2 = NetworkXJSONStore(path)  # reload from disk
        assert s2.get_node("a")["description"] == "updated"
        assert s2.get_node("a")["name"] == "A"
        edges = s2.edges_of("a")
        assert any(k == "uses" for _u, _v, k, _d in edges)

    def test_paths_and_neighborhood(self, tmp_path):
        s = NetworkXJSONStore(tmp_path / "kg.json")
        for n in "abcd":
            s.upsert_node(n, {"name": n})
        s.upsert_edge("a", "b", "r", {})
        s.upsert_edge("b", "c", "r", {})
        s.upsert_edge("c", "d", "r", {})
        paths = s.paths_between("a", "d", cutoff=4)
        assert ["a", "b", "c", "d"] in paths
        assert s.neighborhood("b", 1) == {"a", "b", "c"}

    def test_missing_nodes_are_safe(self, tmp_path):
        s = NetworkXJSONStore(tmp_path / "kg.json")
        assert s.get_node("nope") is None
        assert s.paths_between("x", "y") == []
        assert s.neighborhood("x") == set()
