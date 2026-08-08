"""Core typed vocabulary of the engine.

Everything the pipeline passes between layers is one of these models.
The evidence chain is the load-bearing invariant:

    Document --extraction--> Entity / Claim / Relationship
    Claim  MUST carry >=1 Evidence
    Evidence MUST point at a real fetched Document (source, url, date)

A claim with no evidence is rejected at the validation gate, never stored.
"""

from __future__ import annotations

import hashlib
import re
import uuid
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def normalize_name(name: str) -> str:
    """Canonical key for entity resolution: casefold, strip punctuation runs."""
    return re.sub(r"[^a-z0-9]+", " ", name.casefold()).strip()


# --------------------------------------------------------------------------
# Sources and documents
# --------------------------------------------------------------------------

class SourceCategory(str, Enum):
    ACADEMIC = "academic"
    WEB = "web"
    CODE = "code"
    NEWS = "news"
    GOVERNMENT = "government"
    PATENTS = "patents"
    COMMUNITY = "community"
    DATA = "data"


class SourceStatus(str, Enum):
    LIVE = "live"                # keyless, working
    DEGRADED = "degraded"        # working but unreliable/limited (honest flag)
    NEEDS_KEY = "needs_key"      # adapter present, disabled until a key is set
    ERROR = "error"              # runtime failure this session


class RawDoc(BaseModel):
    """A fetched item from one source, before extraction."""
    url: str
    title: str
    source: str                          # adapter name, e.g. "arxiv"
    category: SourceCategory
    text: str = ""                       # abstract / body excerpt used for extraction
    authors: list[str] = Field(default_factory=list)
    published: datetime | None = None
    extra: dict = Field(default_factory=dict)   # citations, stars, score, etc.

    @property
    def text_hash(self) -> str:
        """Dedupe key: same content re-fetched later is never re-extracted."""
        basis = (self.url + "|" + self.text[:2000]).encode()
        return hashlib.sha256(basis).hexdigest()[:24]


# --------------------------------------------------------------------------
# Evidence-chain models
# --------------------------------------------------------------------------

class EntityType(str, Enum):
    PERSON = "person"
    COMPANY = "company"
    TECHNOLOGY = "technology"
    CONCEPT = "concept"
    EVENT = "event"
    PAPER = "paper"
    PRODUCT = "product"
    ORGANIZATION = "organization"
    PLACE = "place"
    OTHER = "other"


class Entity(BaseModel):
    id: str = Field(default_factory=lambda: new_id("ent"))
    name: str
    type: EntityType = EntityType.OTHER
    description: str = ""
    aliases: list[str] = Field(default_factory=list)
    domains: list[str] = Field(default_factory=list)  # cross-domain reasoning tags
    first_seen: datetime = Field(default_factory=now_utc)
    last_seen: datetime = Field(default_factory=now_utc)

    @property
    def norm_name(self) -> str:
        return normalize_name(self.name)


class Evidence(BaseModel):
    id: str = Field(default_factory=lambda: new_id("ev"))
    source: str                          # adapter name
    category: SourceCategory
    url: str
    title: str = ""
    excerpt: str = ""                    # the text region that grounds the claim
    authors: list[str] = Field(default_factory=list)
    published: datetime | None = None
    fetched_at: datetime = Field(default_factory=now_utc)
    reliability: float = 0.5             # deterministic score, see extraction/reliability.py


class Polarity(str, Enum):
    ASSERTS = "asserts"          # the claim states something is true
    DISPUTES = "disputes"        # the claim states something is false/doubted


class Claim(BaseModel):
    id: str = Field(default_factory=lambda: new_id("clm"))
    statement: str
    entity_ids: list[str] = Field(default_factory=list)
    polarity: Polarity = Polarity.ASSERTS
    evidence: list[Evidence] = Field(default_factory=list)
    confidence: float = 0.0              # deterministic rollup, not LLM vibes
    verified: bool = False               # set only by the Verification agent gate


class Predicate(str, Enum):
    # Spec-required relationship vocabulary
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    DEPENDS_ON = "depends_on"
    CAUSES = "causes"
    RELATED_TO = "related_to"
    CREATED_BY = "created_by"
    FOUNDED = "founded"
    USES = "uses"
    COMPETES_WITH = "competes_with"
    IMPROVES = "improves"
    ENABLES = "enables"
    INTRODUCED_BY = "introduced_by"
    OPTIMIZED_BY = "optimized_by"
    PART_OF = "part_of"


class Relationship(BaseModel):
    id: str = Field(default_factory=lambda: new_id("rel"))
    subject_id: str
    predicate: Predicate
    object_id: str
    evidence_ids: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    first_seen: datetime = Field(default_factory=now_utc)
    last_seen: datetime = Field(default_factory=now_utc)
    sessions: list[str] = Field(default_factory=list)  # historical tracking


class ExtractionResult(BaseModel):
    """Everything one document yielded after the validation gate."""
    doc_url: str
    entities: list[Entity] = Field(default_factory=list)
    claims: list[Claim] = Field(default_factory=list)
    relationships: list[Relationship] = Field(default_factory=list)
    rejected: int = 0                    # items the deterministic gate discarded


# --------------------------------------------------------------------------
# Planning
# --------------------------------------------------------------------------

class AgentSpec(BaseModel):
    """One specialized research worker from the plan roster."""
    name: str                            # e.g. "Academic Research Agent"
    focus: str                           # what this worker hunts for
    sources: list[str]                   # adapter names, in priority order
    queries: list[str]                   # search strings (topic reformulations)
    extraction_emphasis: str = ""        # hint passed to the extractor prompt


class ResearchPlan(BaseModel):
    id: str = Field(default_factory=lambda: new_id("plan"))
    topic: str
    domain: str = ""
    key_entities: list[str] = Field(default_factory=list)
    research_questions: list[str] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)
    conflicting_viewpoints: list[str] = Field(default_factory=list)
    knowledge_gaps: list[str] = Field(default_factory=list)
    known_context: list[str] = Field(default_factory=list)  # what the KG already knows
    agents: list[AgentSpec] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=now_utc)


# --------------------------------------------------------------------------
# Agent findings and the final report
# --------------------------------------------------------------------------

class Finding(BaseModel):
    """Typed output of a graph-reasoning agent. Always cites evidence."""
    agent: str
    kind: str                            # summary | verification | contradiction | discovery | trend | question
    text: str
    entity_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    confidence: float = 0.0


class TimelineEvent(BaseModel):
    date: datetime
    text: str
    source: str
    url: str


class ReportSection(BaseModel):
    title: str
    body_md: str
    item_count: int = 0                  # content-fidelity check: rendered items, not markers


class ResearchReport(BaseModel):
    session_id: str
    topic: str
    generated_at: datetime = Field(default_factory=now_utc)
    sections: list[ReportSection] = Field(default_factory=list)
    stats: dict = Field(default_factory=dict)

    def section(self, title: str) -> ReportSection | None:
        for s in self.sections:
            if s.title == title:
                return s
        return None


# --------------------------------------------------------------------------
# Session state (drives the Context Graph and the API)
# --------------------------------------------------------------------------

class SessionPhase(str, Enum):
    PLANNING = "planning"
    SEARCHING = "searching"
    EXTRACTING = "extracting"
    REASONING = "reasoning"
    CONSOLIDATING = "consolidating"
    REPORTING = "reporting"
    DONE = "done"
    FAILED = "failed"


class ProgressEvent(BaseModel):
    at: datetime = Field(default_factory=now_utc)
    phase: SessionPhase
    message: str
    data: dict = Field(default_factory=dict)
