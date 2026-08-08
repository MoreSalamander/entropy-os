"""Offline fixtures. The suite runs with no network, no Ollama, no npm."""

from __future__ import annotations

import pytest
from research_engine.llm.client import FakeLLM

from code_engine.architecture import ArchitectAgent
from code_engine.graphs.context_graph import SoftwareContextGraph
from code_engine.intent import IntentAnalyzer
from code_engine.models import (ApiEndpoint, Architecture, Component,
                                EntityField, EntityModel, Feature)

REQUEST = "Build an AI research platform that lets users investigate any topic."


@pytest.fixture
async def spec():
    return await IntentAnalyzer(FakeLLM(up=False)).analyze(REQUEST)


@pytest.fixture
async def architecture(spec):
    return await ArchitectAgent(FakeLLM(up=False)).design(spec)


def rich_architecture(spec) -> Architecture:
    """Hand-built two-service architecture for impact/drift tests."""
    feat_a = Feature(name="Topic management", description="CRUD topics",
                     requirement_ids=[spec.requirements[0].id])
    feat_b = Feature(name="Note taking", description="notes on topics",
                     requirement_ids=[spec.requirements[0].id])
    topic = EntityModel(name="Topic", fields=[EntityField(name="title")])
    note = EntityModel(name="Note", fields=[
        EntityField(name="body", type="text"),
        EntityField(name="topic_id", type="int")])
    topics = Component(
        name="topics", purpose="topic registry", feature_ids=[feat_a.id],
        depends_on=["database"], entities=["Topic"],
        endpoints=[
            ApiEndpoint(method="GET", path="/topics", summary="List topics",
                        entity="Topic", action="list"),
            ApiEndpoint(method="POST", path="/topics", summary="Create topic",
                        entity="Topic", action="create"),
            ApiEndpoint(method="GET", path="/topics/{item_id}",
                        summary="Fetch topic", entity="Topic", action="get")])
    notes = Component(
        name="notes", purpose="notes attached to topics",
        feature_ids=[feat_b.id], depends_on=["topics", "database"],
        entities=["Note"],
        endpoints=[
            ApiEndpoint(method="GET", path="/notes", summary="List notes",
                        entity="Note", action="list"),
            ApiEndpoint(method="POST", path="/notes", summary="Create note",
                        entity="Note", action="create")])
    db = Component(name="database", purpose="persistence", kind="store")
    arch = Architecture(features=[feat_a, feat_b],
                        components=[topics, notes, db],
                        entities=[topic, note])
    return arch


@pytest.fixture
def rich_arch(spec):
    return rich_architecture(spec)


def generate_project(tmp_path, spec, arch):
    from code_engine.codegen.generator import ProjectGenerator
    cg = SoftwareContextGraph("proj_test")
    cg.load_spec(spec)
    cg.load_architecture(arch)
    project = ProjectGenerator(tmp_path / "out").generate(spec, arch, cg)
    return project, cg, tmp_path / "out"
