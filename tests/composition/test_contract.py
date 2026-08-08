"""The Universal Engine Contract holds for leaves and composites alike."""

from __future__ import annotations

from entropy_os.composition.contract import ComposableEngine, ExecuteRequest, ExecutionRef

from .conftest import FakeResearch, in_process_remote


async def test_leaf_serves_every_contract_route():
    remote = in_process_remote(FakeResearch())
    manifest = await remote.describe()
    assert manifest.identity.kind == "leaf"
    assert manifest.identity.datahub_platform == "fake-research"
    assert [c.name for c in manifest.capabilities] == ["research.investigate"]
    assert (await remote.health()).status == "ok"
    assert (await remote.state()).executions_total == 0
    assert (await remote.context()).engine == "fake-research"
    assert (await remote.knowledge()).datahub_platform == "fake-research"
    assert await remote.recent_events() == []
    await remote.aclose()


async def test_execute_returns_outputs_events_and_provenance():
    remote = in_process_remote(FakeResearch())
    result = await remote.execute(ExecuteRequest(
        capability="research.investigate", inputs={"topic": "WebGPU"},
        ref=ExecutionRef(objective_id="obj-1")))
    assert result.status == "completed"
    assert result.outputs["topic"] == "WebGPU"
    assert [e.kind for e in result.events] == ["ResearchCompleted"]
    assert result.events[0].objective_id == "obj-1"
    # Provenance points at the ENGINE's own DataHub platform, not a shared one.
    assert result.provenance.datahub_urns == [
        "urn:li:dataset:(urn:li:dataPlatform:fake-research,session.s1,PROD)"]
    assert result.provenance.started_at and result.provenance.finished_at
    await remote.aclose()


async def test_capability_failure_is_a_result_not_a_transport_error():
    """A composite must be able to tell 'it ran and failed' apart from
    'I could not reach it' — so failures come back as status='failed'."""
    remote = in_process_remote(FakeResearch())
    result = await remote.execute(ExecuteRequest(
        capability="research.investigate", inputs={}))    # missing topic
    assert result.status == "failed"
    assert "topic" in result.error
    assert result.provenance.notes, "traceback should be preserved for operators"

    unknown = await remote.execute(ExecuteRequest(capability="nope.nothing"))
    assert unknown.status == "failed"
    assert "unknown capability" in unknown.error
    await remote.aclose()


async def test_remote_and_local_engines_are_interchangeable():
    """RemoteEngine and the adapter it proxies both satisfy the protocol —
    the property the whole architecture rests on."""
    local = FakeResearch()
    remote = in_process_remote(local)
    assert isinstance(local, ComposableEngine)
    assert isinstance(remote, ComposableEngine)
    assert (await local.describe()).identity.name == \
           (await remote.describe()).identity.name
    await remote.aclose()


async def test_ingest_event_records_without_dispatching():
    """Events describe; they never command. Ingesting one must not execute
    anything — that restraint is what preserves engine autonomy."""
    from entropy_os.composition.contract import SemanticEvent
    engine = FakeResearch()
    remote = in_process_remote(engine)
    await remote.ingest_event(SemanticEvent(
        kind="SoftwareBuilt", engine="someone-else", subject="urn:x"))
    state = await remote.state()
    assert state.executions_total == 0, "ingesting a fact must not execute"
    kinds = [e.kind for e in await remote.recent_events()]
    assert kinds == ["SoftwareBuilt"]
    await remote.aclose()
