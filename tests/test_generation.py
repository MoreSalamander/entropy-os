"""Phase 8 + 9: generated software must actually work.

The money test runs the GENERATED project's own pytest suite in a
subprocess — the platform's output is judged by real execution, offline.
"""

from __future__ import annotations

import os
import subprocess
import sys

from code_engine.org import run_static_agents
from code_engine.models import CheckStatus

from conftest import generate_project


def _run_generated_pytest(root) -> tuple[int, str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(root)
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "--no-header", "tests"],
        cwd=root, env=env, capture_output=True, text=True, timeout=180)
    return proc.returncode, proc.stdout + proc.stderr


class TestGeneratedProject:
    def test_project_tree_complete(self, spec, rich_arch, tmp_path):
        project, cg, out = generate_project(tmp_path, spec, rich_arch)
        for required in ("app/main.py", "app/db.py", "app/models.py",
                         "app/schemas.py", "app/routers/topics.py",
                         "app/services/notes.py", "tests/conftest.py",
                         "tests/test_topics.py", "docs/architecture.md",
                         "docs/api.md", "README.md", "Dockerfile",
                         "requirements.txt"):
            assert (out / required).exists(), f"missing {required}"
        assert project.files_written >= 18

    def test_generated_tests_pass_for_real(self, spec, rich_arch, tmp_path):
        _project, _cg, out = generate_project(tmp_path, spec, rich_arch)
        code, output = _run_generated_pytest(out)
        assert code == 0, f"generated project's own tests failed:\n{output[-1500:]}"

    def test_fallback_architecture_also_runs(self, spec, architecture, tmp_path):
        _project, _cg, out = generate_project(tmp_path, spec, architecture)
        code, output = _run_generated_pytest(out)
        assert code == 0, output[-1500:]

    def test_provenance_by_construction(self, spec, rich_arch, tmp_path):
        _project, cg, _out = generate_project(tmp_path, spec, rich_arch)
        # file → component
        assert cg.component_of_file("app/routers/topics.py") == "topics"
        assert cg.component_of_file("app/services/notes.py") == "notes"
        # test → feature chain exists
        tests = cg.nodes_of_kind("test")
        assert tests
        feat_ids = {f_id for f_id, _d in cg.nodes_of_kind("feature")}
        verified = {v for t, _d in tests for v, _p in cg.out_edges(t, "verifies")}
        assert verified <= feat_ids and verified

    def test_static_agents_pass_on_clean_output(self, spec, rich_arch, tmp_path):
        _project, _cg, out = generate_project(tmp_path, spec, rich_arch)
        for result in run_static_agents(out):
            assert result.status == CheckStatus.PASS, (result.check,
                                                       result.failures)

    def test_sidecar_roundtrip(self, spec, rich_arch, tmp_path):
        from code_engine.graphs.context_graph import SoftwareContextGraph
        _project, cg, out = generate_project(tmp_path, spec, rich_arch)
        cg.save_sidecar(out)
        loaded = SoftwareContextGraph.load_sidecar(out)
        assert loaded.stats() == cg.stats()
        assert loaded.component_of_file("app/routers/topics.py") == "topics"


class TestLiveRunRegressions:
    """Shapes the first live run exposed — locked in as offline regressions."""

    async def _arch_from_proposal(self, spec, proposal):
        from research_engine.llm.client import FakeLLM
        from code_engine.architecture import ArchitectAgent
        return await ArchitectAgent(FakeLLM({"plan": [proposal]})).design(spec)

    async def test_llm_param_names_normalized_and_tests_green(self, spec, tmp_path):
        # live run: LLM proposed /datasets/{id}; handlers bind item_id → 422s
        proposal = {
            "features": [], "entities": [
                {"name": "Dataset", "fields": [{"name": "title", "type": "str"}]}],
            "components": [{"name": "dataset_service", "purpose": "p",
                            "feature_names": [], "depends_on": [],
                            "entities": ["Dataset"],
                            "endpoints": [
                                {"method": "GET", "path": "/datasets",
                                 "summary": "list", "entity": "Dataset"},
                                {"method": "POST", "path": "/datasets",
                                 "summary": "create", "entity": "Dataset"},
                                {"method": "GET", "path": "/datasets/{dataset_id}",
                                 "summary": "get one", "entity": "Dataset"}]}],
        }
        arch = await self._arch_from_proposal(spec, proposal)
        svc = next(c for c in arch.components if c.name == "dataset_service")
        get_ep = next(ep for ep in svc.endpoints if ep.action == "get")
        assert "{item_id}" in get_ep.path  # normalized
        _p, _cg, out = generate_project(tmp_path, spec, arch)
        code, output = _run_generated_pytest(out)
        assert code == 0, output[-1200:]

    async def test_stub_only_router_is_ruff_clean(self, spec, tmp_path):
        # live run: routers with only custom stubs carried dead imports (F401)
        proposal = {
            "features": [], "entities": [
                {"name": "Thing", "fields": [{"name": "title", "type": "str"}]}],
            "components": [
                {"name": "things", "purpose": "p", "feature_names": [],
                 "depends_on": [], "entities": ["Thing"], "endpoints": []},
                {"name": "access_control", "purpose": "stub-only service",
                 "feature_names": [], "depends_on": [], "entities": [],
                 "endpoints": [{"method": "GET", "path": "/access/policies",
                                "summary": "custom", "entity": ""}]}],
        }
        arch = await self._arch_from_proposal(spec, proposal)
        _p, _cg, out = generate_project(tmp_path, spec, arch)
        env = dict(os.environ)
        proc = subprocess.run(
            [sys.executable, "-m", "ruff", "check", "app", "tests"],
            cwd=out, env=env, capture_output=True, text=True, timeout=60)
        assert proc.returncode == 0, proc.stdout[-1200:]
        code, output = _run_generated_pytest(out)
        assert code == 0, output[-1200:]

    def test_generated_projects_are_ruff_clean(self, spec, rich_arch, tmp_path):
        _p, _cg, out = generate_project(tmp_path, spec, rich_arch)
        proc = subprocess.run(
            [sys.executable, "-m", "ruff", "check", "app", "tests"],
            cwd=out, capture_output=True, text=True, timeout=60)
        assert proc.returncode == 0, proc.stdout[-1200:]


class TestStaticAgentsFire:
    def test_security_agent_flags_seeded_defects(self, spec, rich_arch, tmp_path):
        _p, _cg, out = generate_project(tmp_path, spec, rich_arch)
        svc = out / "app/services/topics.py"
        svc.write_text(svc.read_text() +
                       "\n\ndef unsafe(x):\n    return eval(x)\n")
        results = {r.check: r for r in run_static_agents(out)}
        assert results["security"].status == CheckStatus.FAIL
        assert any("eval" in f["message"] for f in results["security"].failures)

    def test_performance_agent_flags_query_in_loop(self, spec, rich_arch, tmp_path):
        _p, _cg, out = generate_project(tmp_path, spec, rich_arch)
        svc = out / "app/services/notes.py"
        svc.write_text(svc.read_text() + (
            "\n\ndef n_plus_one(session, ids):\n"
            "    out = []\n"
            "    for i in ids:\n"
            "        out.append(session.get(models.Note, i))\n"
            "    return out\n"))
        results = {r.check: r for r in run_static_agents(out)}
        assert results["performance"].status == CheckStatus.FAIL

    def test_review_agent_flags_layer_violation(self, spec, rich_arch, tmp_path):
        _p, _cg, out = generate_project(tmp_path, spec, rich_arch)
        router = out / "app/routers/topics.py"
        router.write_text("from app import models\n" + router.read_text())
        results = {r.check: r for r in run_static_agents(out)}
        assert results["review"].status == CheckStatus.FAIL
        assert any("service layer" in f["message"]
                   for f in results["review"].failures)
