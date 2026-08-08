"""Test fixtures: fake engines and in-process contract servers.

The tests exercise the ARCHITECTURE, not the four real engines: composition,
recursion, event semantics, and provenance must hold regardless of what a
member actually does. Fakes make those claims testable in milliseconds with
no Ollama, no DataHub, and no Temporal.
"""

from __future__ import annotations

import httpx
import pytest

from one_engine.adapters.base import LeafAdapter
from one_engine.composite import CompositeEngine
from one_engine.contract import ArtifactRef, CapabilitySpec, ExecuteRequest, FieldSpec
from one_engine.contract.http import build_engine_app
from one_engine.events.bus import EventBus
from one_engine.federation.datahub import FederationBridge
from one_engine.remote import RemoteEngine


class FakeResearch(LeafAdapter):
    name = "fake-research"
    description = "fake research engine"
    datahub_platform = "fake-research"
    events_emitted = ["ResearchCompleted"]

    def capabilities(self) -> list[CapabilitySpec]:
        return [CapabilitySpec(
            name="research.investigate", summary="fake research",
            inputs={"topic": FieldSpec(type="string", required=True)})]

    async def _run(self, req: ExecuteRequest, emit):
        topic = req.inputs["topic"]
        urn = self.dataset_urn("session.s1")
        emit("ResearchCompleted", subject=urn, topic=topic)
        return ({"session_id": "s1", "topic": topic,
                 "findings": [f"{topic} is real"]},
                [ArtifactRef(kind="report", path="/tmp/r.md")], [urn], [])


class FakeUniversity(LeafAdapter):
    name = "fake-university"
    description = "fake university engine"
    datahub_platform = "fake-university"
    events_emitted = ["CurriculumCreated"]

    def capabilities(self) -> list[CapabilitySpec]:
        return [CapabilitySpec(
            name="university.design_curriculum", summary="fake curriculum",
            inputs={"goal": FieldSpec(type="string", required=True)})]

    async def _run(self, req: ExecuteRequest, emit):
        goal = req.inputs["goal"]
        urn = self.dataset_urn("session.c1")
        emit("CurriculumCreated", subject=urn, goal=goal)
        return ({"session_id": "c1", "subject": "fake",
                 "learning_order": ["basics", "internals", "practice"]},
                [], [urn], [])


class FakeSoftware(LeafAdapter):
    name = "fake-software"
    description = "fake software engine"
    datahub_platform = "fake-software"
    events_emitted = ["SoftwareBuilt"]

    def capabilities(self) -> list[CapabilitySpec]:
        return [CapabilitySpec(
            name="software.build", summary="fake build",
            inputs={"request": FieldSpec(type="string", required=True)})]

    async def _run(self, req: ExecuteRequest, emit):
        urn = self.dataset_urn("project.p1")
        emit("SoftwareBuilt", subject=urn)
        # Echo the request so tests can prove upstream outputs reached here.
        return ({"project_id": "p1", "product_name": "FakeAcademy",
                 "received_request": req.inputs["request"],
                 "verification_passed": True},
                [ArtifactRef(kind="project", path="/tmp/p1")], [urn], [])


class FakeWeb(LeafAdapter):
    name = "fake-web"
    description = "fake web engine"
    datahub_platform = "fake-web"
    events_emitted = ["SiteGenerated"]

    def capabilities(self) -> list[CapabilitySpec]:
        return [CapabilitySpec(
            name="web.generate_site", summary="fake site",
            inputs={"request": FieldSpec(type="string", required=True)})]

    async def _run(self, req: ExecuteRequest, emit):
        urn = self.dataset_urn("project.w1")
        emit("SiteGenerated", subject=urn)
        return ({"project_id": "w1", "received_request": req.inputs["request"],
                 "pages": ["home", "about"]},
                [ArtifactRef(kind="site", path="/tmp/w1")], [urn], [])


def in_process_remote(engine, base_url: str = "http://engine.test") -> RemoteEngine:
    """A RemoteEngine that speaks the real HTTP contract to an ASGI app in
    this process. The class under test is unmodified — only its transport is
    swapped — so what the tests exercise is the genuine remote path."""
    app = build_engine_app(engine)
    remote = RemoteEngine(base_url)
    remote._client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url=base_url)
    return remote


@pytest.fixture
def offline_federation(tmp_path):
    """A federation bridge pointed at a port nothing listens on: proves the
    system stays functional and honest when DataHub is absent."""
    return FederationBridge(gms_url="http://127.0.0.1:9", platform="test")


@pytest.fixture
def bus(tmp_path):
    return EventBus(tmp_path / "events.jsonl")


@pytest.fixture
def members():
    return {"research": FakeResearch(), "university": FakeUniversity(),
            "software": FakeSoftware(), "web": FakeWeb()}


@pytest.fixture
def unified(members, bus, offline_federation):
    """The unified system, consuming its four members over the real contract
    transport — exactly as it does in deployment."""
    return CompositeEngine(
        name="one-engine",
        members={k: in_process_remote(v, f"http://{k}.test")
                 for k, v in members.items()},
        bus=bus, federation=offline_federation,
        datahub_platform="one-engine")
