"""Phases 7, 10, 11, 12: codebase model, impact analysis, drift, KG memory."""

from __future__ import annotations

from entropy_os.engines.research.llm.client import FakeLLM
from entropy_os.engines.research.graphs.store import NetworkXJSONStore
from entropy_os.engines.research.graphs.vector_index import VectorIndex

from entropy_os.engines.software.graphs.codebase_model import CodebaseAnalyzer
from entropy_os.engines.software.graphs.knowledge_graph import SoftwareKnowledgeGraph
from entropy_os.engines.software.impact import analyze_impact, impact_markdown
from entropy_os.engines.software.models import ProjectOutcome, ResearchEvidence
from entropy_os.engines.software.verify import Verifier

from .conftest import generate_project


class TestImpactAnalysis:
    def test_transitive_dependents_and_chain(self, spec, rich_arch, tmp_path):
        _p, cg, out = generate_project(tmp_path, spec, rich_arch)
        cg.save_sidecar(out)
        # topics is depended on by notes → changing topics ripples to notes
        report = analyze_impact(cg, "topics")
        assert "notes" in report.dependent_components
        assert any("/topics" in api for api in report.affected_apis)
        assert any("/notes" in api for api in report.affected_apis)  # ripple
        assert any("test_topic" in t for t in report.affected_tests)
        assert report.affected_requirements
        assert any("architecture.md" in d for d in report.stale_docs)
        assert report.infra_touchpoints  # topics owns an entity → schema reach

    def test_leaf_component_has_no_dependents(self, spec, rich_arch, tmp_path):
        _p, cg, _out = generate_project(tmp_path, spec, rich_arch)
        report = analyze_impact(cg, "notes")
        assert report.dependent_components == []
        md = impact_markdown(report)
        assert "## Dependent components" in md and "(none)" in md

    def test_unknown_component_raises(self, spec, rich_arch, tmp_path):
        _p, cg, _out = generate_project(tmp_path, spec, rich_arch)
        try:
            analyze_impact(cg, "ghost")
            raise AssertionError("should have raised")
        except KeyError:
            pass


class TestDriftDetection:
    def test_clean_generation_has_no_blockers(self, spec, rich_arch, tmp_path):
        _p, cg, out = generate_project(tmp_path, spec, rich_arch)
        findings = CodebaseAnalyzer(out).drift_report(cg)
        assert not [f for f in findings if f.severity == "blocker"], findings

    def test_rogue_file_and_undeclared_import_flagged(self, spec, rich_arch,
                                                      tmp_path):
        _p, cg, out = generate_project(tmp_path, spec, rich_arch)
        (out / "app" / "rogue.py").write_text("x = 1\n")
        svc = out / "app" / "services" / "topics.py"
        svc.write_text("from app.services import notes as sneaky\n"
                       + svc.read_text())
        findings = CodebaseAnalyzer(out).drift_report(cg)
        kinds = [(f.kind, f.message) for f in findings]
        assert any("rogue.py" in m for _k, m in kinds)
        assert any("imports 'notes'" in m and "no depends_on" in m
                   for _k, m in kinds)

    def test_deleted_modeled_file_is_blocker(self, spec, rich_arch, tmp_path):
        _p, cg, out = generate_project(tmp_path, spec, rich_arch)
        (out / "app" / "services" / "notes.py").unlink()
        findings = CodebaseAnalyzer(out).drift_report(cg)
        assert any(f.severity == "blocker" and "notes.py" in f.message
                   for f in findings)


class TestVerifierGates:
    async def test_repair_rejects_bad_patches(self, spec, rich_arch, tmp_path):
        _p, cg, out = generate_project(tmp_path, spec, rich_arch)
        failure = {"file": "tests/test_topics.py", "test": "t",
                   "component": "topics"}
        # syntax-error patch → rejected
        v = Verifier(FakeLLM({"extract": [
            {"file": "app/routers/topics.py", "content": "def broken(:",
             "explanation": "x"}]}))
        assert not await v._attempt_repair(out, failure, "boom", cg)
        # patch targeting tests → rejected
        v2 = Verifier(FakeLLM({"extract": [
            {"file": "tests/test_topics.py", "content": "x = 1\n",
             "explanation": "x"}]}))
        assert not await v2._attempt_repair(out, failure, "boom", cg)
        # path escape → rejected
        v3 = Verifier(FakeLLM({"extract": [
            {"file": "../outside.py", "content": "x = 1\n",
             "explanation": "x"}]}))
        assert not await v3._attempt_repair(out, failure, "boom", cg)

    async def test_verification_reports_honestly_when_repair_unavailable(
            self, spec, rich_arch, tmp_path):
        _p, cg, out = generate_project(tmp_path, spec, rich_arch)
        # sabotage the service so its tests fail
        svc = out / "app" / "services" / "topics.py"
        svc.write_text(svc.read_text().replace(
            "session.commit()", "pass  # commit removed", 1))
        report = await Verifier(FakeLLM(up=False)).verify(
            out, cg, log=lambda *_: None)
        assert not report.passed
        assert report.known_problems  # red suite stays red in the report
        # failure mapped into the graph as problem nodes
        assert cg.nodes_of_kind("problem")


class TestKnowledgeGraphMemory:
    async def test_absorb_and_pattern_priors(self, tmp_path):
        kg = SoftwareKnowledgeGraph(
            NetworkXJSONStore(tmp_path / "kg.json"),
            VectorIndex(FakeLLM(), path=tmp_path / "q"))
        await kg.absorb_evidence([ResearchEvidence(
            agent="Technology Research Agent", topic="technology",
            title="fastapi 0.115.6", url="https://pypi.org/project/fastapi/",
            summary="web framework", extra={"version": "0.115.6"})])
        risk = kg.technology_risk("fastapi")
        assert risk and risk["latest_version"] == "0.115.6"

        kg.record_outcome(ProjectOutcome(
            project_id="p1", product_name="X", components=3, entities=2,
            endpoints=8, tests_generated=5, verification_passed=True,
            repair_rounds=0, patterns=["router_service_split"]))
        kg.record_outcome(ProjectOutcome(
            project_id="p2", product_name="Y", components=2, entities=1,
            endpoints=4, tests_generated=3, verification_passed=False,
            repair_rounds=2, patterns=["router_service_split"]))
        priors = kg.pattern_priors()
        top = next(p for p in priors if p["pattern"] == "router_service_split")
        assert top["applied"] == 2
        assert top["success_rate"] == 0.5
        assert top["avg_repair_rounds"] == 1.0
