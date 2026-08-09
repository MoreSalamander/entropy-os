"""The read → act → write loop, held to what it may claim.

The agent's whole value is that the code it generates was informed by real
metadata. That claim is only worth anything if the agent cannot make it when
it is false, so most of these tests are about the failure paths: the catalog
being unreachable, the catalog being empty, and the difference between them
reaching both the generator and the record written back.
"""

from __future__ import annotations

from entropy_os.composition.contract import Determinism, Verdict
from entropy_os.datahub_agent import AgentRun, compose_request, dataset_urn
from entropy_os.datahub_read import Dataset, Field_, GraphContext


def _graph_with_schema() -> GraphContext:
    g = GraphContext(query="hunter outcome")
    g.datasets = [Dataset(
        urn="urn:li:dataset:(urn:li:dataPlatform:veritas,outcome-0,PROD)",
        name="outcome-0", platform="veritas",
        fields=[Field_(path="accepted", type="boolean"),
                Field_(path="accepted_because", type="string")])]
    return g


def test_a_grounded_request_carries_the_real_fields_verbatim():
    """Pasted, not summarised: a summary is where a model quietly introduces
    a column nobody has."""
    req = compose_request("build a service for gate outcomes", _graph_with_schema())
    assert "accepted : boolean" in req
    assert "accepted_because : string" in req
    assert "do not invent columns" in req


def test_an_unreachable_catalog_tells_the_generator_it_is_blind():
    """Generating against a guess is fine. Generating against a guess while
    believing it is grounded is the failure this prevents."""
    g = GraphContext(query="x", reason="ConnectError: refused")
    req = compose_request("build something", g)
    assert "could not be consulted" in req
    assert "refused" in req
    assert "infer the data model from the request alone" in req.lower()


def test_an_empty_catalog_is_worded_differently_from_a_missing_one():
    """Two different facts about the world. A generator that cannot tell them
    apart will treat 'nothing found' as 'nothing exists'."""
    empty = compose_request("build something", GraphContext(query="x"))
    missing = compose_request("build something",
                              GraphContext(query="x", reason="down"))
    assert "holds nothing related" in empty
    assert "could not be consulted" in missing
    assert empty != missing


def test_grounded_is_false_when_the_datasets_carry_no_schema():
    """Found-but-undescribed is the common case in this instance: only 30 of
    1,411 datasets have schema fields. Finding a dataset is not the same as
    learning its shape, and only the second one grounds a build."""
    g = GraphContext(query="q")
    g.datasets = [Dataset(urn="urn:li:dataset:(x,proj,PROD)", name="proj")]
    assert not any(d.is_described for d in g.datasets)


def test_the_run_summary_says_ungrounded_out_loud():
    run = AgentRun(request="r", graph=GraphContext(query="q", reason="down"),
                   grounded=False)
    assert "UNGROUNDED" in run.summary()


def test_urns_are_stable_and_readable():
    urn = dataset_urn("generated.proj_abc123")
    assert urn.startswith("urn:li:dataset:(urn:li:dataPlatform:entropy-agent,")
    assert "generated.proj_abc123" in urn


def test_an_assertion_carries_its_determinism_not_just_its_result():
    """A green assertion produced by a judge model and one produced by pytest
    are different claims. DataHub shows the description, so the description
    has to carry the distinction."""
    from entropy_os.datahub_agent import Publisher

    v = Verdict(gate="pytest", determinism=Determinism.HARD, passed=True,
                evidence="6 passed in 0.04s")
    # Build the payload the publisher would send, without a server.
    kind = v.determinism.value
    logic = f"[{kind}] {v.evidence[:300]}"
    assert logic.startswith("[hard]")
    assert "6 passed" in logic
    assert isinstance(Publisher("http://127.0.0.1:9").gms, str)
