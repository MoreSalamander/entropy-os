"""Phase 1 + 5: intent floor and architecture gates."""

from __future__ import annotations

from entropy_os.engines.research.llm.client import FakeLLM
from entropy_os.engines.software.architecture import ArchitectAgent
from entropy_os.engines.software.intent import IntentAnalyzer
from entropy_os.engines.software.models import Priority


class TestIntent:
    async def test_fallback_spec_is_buildable(self, spec):
        assert spec.product_name
        assert any(r.kind == "functional" and r.priority == Priority.MUST
                   for r in spec.requirements)

    async def test_baselines_injected(self, spec):
        blob = " ".join(r.text.casefold() for r in spec.requirements)
        assert "test" in blob        # automated tests baseline
        assert "validate" in blob    # input validation baseline

    async def test_llm_proposal_validated(self):
        proposal = {"product_name": "X", "purpose": "p", "user_types": ["u"],
                    "requirements": [
                        {"kind": "bogus_kind", "text": "do a thing",
                         "priority": "must"},
                        {"kind": "functional", "text": "", "priority": "must"}],
                    "technical_constraints": [], "unknowns": [],
                    "dependencies": [], "candidate_approaches": []}
        spec = await IntentAnalyzer(FakeLLM({"plan": [proposal]})).analyze("x")
        kinds = {r.kind for r in spec.requirements}
        assert "bogus_kind" not in kinds          # invalid kind coerced
        assert all(r.text for r in spec.requirements)  # empty text dropped


class TestArchitectureGates:
    async def test_fallback_architecture_complete(self, architecture):
        names = {c.name for c in architecture.components}
        assert "database" in names
        # every MUST functional requirement covered by some feature
        covered = {rid for f in architecture.features for rid in f.requirement_ids}
        assert covered, "no requirement coverage at all"
        # entities get CRUD injected
        service = next(c for c in architecture.components if c.kind == "service")
        actions = {ep.action for ep in service.endpoints}
        assert {"list", "create", "get", "delete"} <= actions

    async def test_uncovered_must_requirement_gets_auto_feature(self, spec):
        proposal = {
            "features": [{"name": "Only one", "description": "d",
                          "requirement_texts": ["nonexistent requirement"]}],
            "entities": [{"name": "Thing", "fields": [{"name": "title",
                                                       "type": "str"}]}],
            "components": [{"name": "core", "purpose": "p",
                            "feature_names": ["Only one"], "depends_on": [],
                            "entities": ["Thing"], "endpoints": []}],
        }
        arch = await ArchitectAgent(FakeLLM({"plan": [proposal]})).design(spec)
        assert any(n.startswith("MUST requirement uncovered")
                   for n in arch.validation_notes)
        auto = [f for f in arch.features if f.name.startswith("Cover:")]
        assert auto and all(f.requirement_ids for f in auto)

    async def test_malformed_endpoint_and_dangling_dep_dropped(self, spec):
        proposal = {
            "features": [], "entities": [{"name": "Thing", "fields": [
                {"name": "title", "type": "str"}]}],
            "components": [{"name": "core", "purpose": "p", "feature_names": [],
                            "depends_on": ["ghost_service"],
                            "entities": ["Thing"],
                            "endpoints": [{"method": "GET",
                                           "path": "not a path!!",
                                           "summary": "s", "entity": "Thing"}]}],
        }
        arch = await ArchitectAgent(FakeLLM({"plan": [proposal]})).design(spec)
        core = next(c for c in arch.components if c.name == "core")
        assert "ghost_service" not in core.depends_on
        assert all(ep.path.startswith("/") for ep in core.endpoints)
        # CRUD was still injected for the owned entity
        assert any(ep.action == "create" for ep in core.endpoints)

    async def test_entity_single_ownership(self, spec):
        proposal = {
            "features": [], "entities": [{"name": "Shared", "fields": [
                {"name": "x", "type": "str"}]}],
            "components": [
                {"name": "a", "purpose": "p", "feature_names": [],
                 "depends_on": [], "entities": ["Shared"], "endpoints": []},
                {"name": "b", "purpose": "p", "feature_names": [],
                 "depends_on": [], "entities": ["Shared"], "endpoints": []}],
        }
        arch = await ArchitectAgent(FakeLLM({"plan": [proposal]})).design(spec)
        owners = [c.name for c in arch.components if "Shared" in c.entities]
        assert owners == ["a"]  # second claim rejected — one owner per entity
