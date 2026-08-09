"""P31c1 — the hosted wedge: a stranger's run is identified, isolated, persisted, and gated.

The load-bearing property is FAIL CLOSED: with no live sandbox, an untrusted goal must be REFUSED
before any model-authored code can execute — never run on the host. Then: a bad token is refused, a
good one runs the gated Software pipeline into the tenant's OWN memory, and two tenants cannot see
each other's runs. (Real containment is proven live in test_container_executor; here the sandbox check
is injected so the wedge's own logic is tested offline.)
"""

from __future__ import annotations

import json

import pytest
from engine.model import ScriptedProvider

from entropy_os.wedge import SandboxUnavailable, Unauthorized, Wedge, WedgeAuth

GOOD_SPEC = json.dumps({
    "function_name": "add", "description": "add two numbers", "signature": "def add(a, b)",
    "cases": [{"args": [1, 2], "expected": 3}, {"args": [5, 5], "expected": 10}],
})
GOOD_CODE = "def add(a, b):\n    return a + b\n"


def _provider() -> ScriptedProvider:
    return ScriptedProvider({"spec": GOOD_SPEC, "developer": GOOD_CODE})


def _wedge(tmp_path, *, sandbox=True, tokens=None) -> Wedge:
    auth = WedgeAuth(tokens or {"tok_alice": "alice"})
    return Wedge(tmp_path, _provider, auth, sandbox_check=lambda: sandbox)


# --- auth: the identity floor ----------------------------------------------------------------

def test_missing_token_is_unauthorized(tmp_path):
    with pytest.raises(Unauthorized):
        _wedge(tmp_path).submit(authorization=None, goal="add two numbers")


def test_unknown_token_is_unauthorized(tmp_path):
    with pytest.raises(Unauthorized):
        _wedge(tmp_path).submit(authorization="Bearer nope", goal="add two numbers")


def test_bearer_and_bare_tokens_both_resolve():
    auth = WedgeAuth({"tok_alice": "alice"})
    assert auth.tenant_for("Bearer tok_alice") == "alice"
    assert auth.tenant_for("tok_alice") == "alice"


def test_empty_token_table_means_the_wedge_is_closed():
    auth = WedgeAuth.from_env(raw="")
    with pytest.raises(Unauthorized):
        auth.tenant_for("Bearer anything")


def test_from_env_parses_pairs_and_rejects_bad_tenant_ids():
    auth = WedgeAuth.from_env(raw="tok_a:alice, tok_b:bob, tok_c:Bad/Id, tok_d:")
    assert auth.tokens == {"tok_a": "alice", "tok_b": "bob"}  # the malformed entries are dropped


# --- THE load-bearing property: fail closed --------------------------------------------------

def test_no_sandbox_refuses_before_any_run(tmp_path):
    w = _wedge(tmp_path, sandbox=False)
    with pytest.raises(SandboxUnavailable):
        w.submit(authorization="Bearer tok_alice", goal="add two numbers")
    assert not (tmp_path / "tenants").exists()  # refused BEFORE touching the tenant's storage


def test_fail_closed_is_checked_after_auth(tmp_path):
    # an anonymous request fails on identity, not on the sandbox — order matters
    w = _wedge(tmp_path, sandbox=False)
    with pytest.raises(Unauthorized):
        w.submit(authorization=None, goal="add two numbers")


# --- the happy path: isolated, persisted, gated ----------------------------------------------

def test_unvendable_slot_is_refused_before_the_sandbox(tmp_path):
    """The allowlist is deterministic and sits before any execution concern:
    an org not on the machine is refused even with a healthy sandbox."""
    from entropy_os.wedge import OrgNotVendable, Wedge, WedgeAuth

    wedge = Wedge(tmp_path, lambda: None, WedgeAuth({"tok": "tenant1"}),
                  sandbox_check=lambda: True)
    with pytest.raises(OrgNotVendable):
        wedge.submit(authorization="Bearer tok", goal="x", org="production")


# --- the contract path: what the wedge itself is responsible for ------------
#
# The slots no longer run studios in this process; they call capabilities.
# So these test the wedge's OWN job — routing, tenancy, the acceptance rule,
# metering, and what lands in the tray — against a fake engine, rather than
# re-testing engines that have their own suites.


def _result(*, status="completed", verdicts=(), outputs=None, artifacts=()):
    """A contract ExecuteResult, as JSON, the way the client returns it."""
    return {
        "status": status,
        "outputs": dict(outputs or {}),
        "artifacts": [dict(a) for a in artifacts],
        "verdicts": [dict(v) for v in verdicts],
        "provenance": {"ref": {"execution_id": "exec-test"}},
        "error": "" if status == "completed" else "the engine gave up",
    }


def _hard(gate="pytest", passed=True):
    return {"gate": gate, "determinism": "hard", "passed": passed,
            "evidence": f"{gate}: {'ok' if passed else 'failed'}", "facts": {}}


def _wedge_with(tmp_path, execute, read_artifact=None, **kw):
    auth = WedgeAuth(kw.pop("tokens", None) or {"tok_alice": "alice"})
    return Wedge(tmp_path, _provider, auth, sandbox_check=lambda: True,
                 execute=execute,
                 read_artifact=read_artifact or (lambda path: {"text": f"<{path}>"}),
                 **kw)


def test_a_slot_routes_to_its_capability_and_carries_the_goal(tmp_path):
    seen = {}

    def execute(capability, inputs):
        seen["capability"], seen["inputs"] = capability, inputs
        return _result(verdicts=[_hard()])

    res = _wedge_with(tmp_path, execute).submit(
        authorization="Bearer tok_alice", goal="add two numbers", org="software")
    assert seen["capability"] == "software.build"
    assert seen["inputs"]["request"] == "add two numbers"
    assert res.accepted is True


def test_the_acceptance_rule_decides_not_the_engines_own_optimism(tmp_path):
    """An engine that completed but proved nothing is not an accepted vend.
    This is the rule the tray's SHIPPED label rests on."""
    res = _wedge_with(tmp_path, lambda c, i: _result(verdicts=[])).submit(
        authorization="Bearer tok_alice", goal="x", org="software")
    assert res.accepted is False

    res = _wedge_with(tmp_path, lambda c, i: _result(
        verdicts=[_hard("ruff"), _hard("pytest", passed=False)])).submit(
        authorization="Bearer tok_alice", goal="x", org="software")
    assert res.accepted is False
    # …and the reasoning is handed to the visitor, not just the conclusion.
    assert any(not g["passed"] for g in res.evidence)


def test_the_software_slot_is_scoped_to_the_tenants_own_directory(tmp_path):
    """Tenancy is the wedge's promise. Where the capability accepts a scope,
    the wedge must actually use it."""
    seen = {}

    def execute(capability, inputs):
        seen.update(inputs)
        return _result(verdicts=[_hard()])

    _wedge_with(tmp_path, execute).submit(
        authorization="Bearer tok_alice", goal="x", org="software")
    assert str(tmp_path / "tenants" / "alice" / "software") in seen["out_dir"]


def test_the_learn_slot_is_scoped_to_the_tenants_own_learner(tmp_path):
    seen = {}

    def execute(capability, inputs):
        seen.update({"cap": capability, **inputs})
        return _result(verdicts=[_hard("roadmap")])

    _wedge_with(tmp_path, execute).submit(
        authorization="Bearer tok_alice", goal="teach me x", org="learn")
    assert seen["cap"] == "university.design_curriculum"
    assert seen["learner_name"] == "alice"


def test_an_unreachable_engine_is_not_a_rejection(tmp_path):
    """Down and refused are different facts. Reporting an outage as 'not
    accepted' would blame the visitor's request for the operator's problem —
    and would charge them for it."""
    from entropy_os.engine_client import EngineUnreachable
    from entropy_os.wedge import SourcesUnavailable

    def execute(capability, inputs):
        raise EngineUnreachable("connection refused")

    with pytest.raises(SourcesUnavailable):
        _wedge_with(tmp_path, execute).submit(
            authorization="Bearer tok_alice", goal="x", org="software")


def test_a_research_report_is_fetched_into_the_tray(tmp_path):
    """A visitor must be able to READ what was made, not just be told it
    exists somewhere on the operator's disk."""
    def execute(capability, inputs):
        return _result(verdicts=[_hard("claims_verified")],
                       outputs={"report_path": "/engines/research/reports/s1.md"})

    res = _wedge_with(tmp_path, execute,
                      read_artifact=lambda p: {"text": "# Findings\n"}).submit(
        authorization="Bearer tok_alice", goal="webgpu", org="research")
    tray = {a["label"]: a["payload"] for a in res.artifacts}
    assert tray["grounded report"] == "# Findings\n"


def test_a_directory_artifact_is_named_rather_than_silently_dropped(tmp_path):
    """A generated project cannot be inlined. Saying so is better than an
    empty tray that implies nothing was produced."""
    from entropy_os.engine_client import EngineUnreachable

    def execute(capability, inputs):
        return _result(verdicts=[_hard()],
                       artifacts=[{"kind": "project", "path": "/out/proj_1",
                                   "description": "generated project"}])

    def read_artifact(path):
        raise EngineUnreachable("it is a directory")

    res = _wedge_with(tmp_path, execute, read_artifact=read_artifact).submit(
        authorization="Bearer tok_alice", goal="x", org="software")
    labels = [a["label"] for a in res.artifacts]
    assert "project (directory)" in labels
    assert any("/out/proj_1" in a["payload"] for a in res.artifacts)


def test_two_tenants_stay_in_their_own_directories(tmp_path):
    seen = []
    w = _wedge_with(tmp_path, lambda c, i: (seen.append(i), _result(verdicts=[_hard()]))[1],
                    tokens={"tok_alice": "alice", "tok_bob": "bob"})
    w.submit(authorization="Bearer tok_alice", goal="x", org="software")
    w.submit(authorization="Bearer tok_bob", goal="x", org="software")
    assert "/alice/" in seen[0]["out_dir"] and "/bob/" in seen[1]["out_dir"]
    assert "/bob/" not in seen[0]["out_dir"]
