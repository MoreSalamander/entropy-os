"""Shared fixtures: canned extraction payloads and evidence-chain builders.

Everything here is offline and deterministic — the suite must pass with no
network, no Ollama, no servers.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from entropy_os.engines.research.models import (
    Claim,
    Entity,
    EntityType,
    Evidence,
    Polarity,
    RawDoc,
    ResearchPlan,
    SourceCategory,
)


def make_doc(url: str = "https://example.org/a", title: str = "Doc A",
             source: str = "arxiv", text: str = "Some abstract text.",
             days_old: int = 10, **extra) -> RawDoc:
    return RawDoc(url=url, title=title, source=source,
                  category=SourceCategory.ACADEMIC, text=text,
                  published=datetime.now(UTC) - timedelta(days=days_old),
                  extra=extra)


def make_evidence(source: str = "arxiv", reliability: float = 0.8,
                  days_old: int = 10, url: str = "https://example.org/a") -> Evidence:
    return Evidence(source=source, category=SourceCategory.ACADEMIC, url=url,
                    title=f"paper via {source}", excerpt="…",
                    published=datetime.now(UTC) - timedelta(days=days_old),
                    reliability=reliability)


def make_claim(statement: str, entity_ids: list[str],
               evidence: list[Evidence], polarity: Polarity = Polarity.ASSERTS) -> Claim:
    return Claim(statement=statement, entity_ids=entity_ids,
                 polarity=polarity, evidence=evidence,
                 confidence=max(e.reliability for e in evidence))


@pytest.fixture
def plan() -> ResearchPlan:
    return ResearchPlan(
        topic="test topic",
        research_questions=["What is the state of quantum error correction?"],
        unknowns=["Scaling limits"])


@pytest.fixture
def entities() -> dict[str, Entity]:
    return {
        "qc": Entity(name="Quantum Computing", type=EntityType.TECHNOLOGY,
                     description="computation using qubits"),
        "ibm": Entity(name="IBM", type=EntityType.COMPANY,
                      description="technology company"),
    }
