"""Evidence Extraction Layer.

RawDoc → Entities + Claims + Relationships, with a hard deterministic gate
between the LLM's proposal and anything the graphs will store:

  * every entity needs a non-empty name and a valid type
  * every claim needs a non-empty statement AND is bound to Evidence built
    deterministically from the fetched document (source, url, date, author,
    reliability) — the LLM cannot invent provenance because it never
    supplies provenance, only text
  * every relationship must connect two entities that exist in the same
    proposal and use a predicate from the fixed vocabulary
  * anything failing the gate is counted in `rejected`, never stored

If the LLM is unavailable the extractor degrades to deterministic-only mode:
the document itself becomes a PAPER/OTHER entity with metadata, no claims
are fabricated, and the run report marks extraction as degraded.
"""

from __future__ import annotations

from ..llm.client import LLMClient, LLMUnavailable
from ..models import (Claim, Entity, EntityType, Evidence, ExtractionResult,
                      Polarity, Predicate, RawDoc, Relationship)
from .reliability import score_reliability

_EXTRACT_SCHEMA = {
    "type": "object",
    "properties": {
        "entities": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "type": {"type": "string",
                             "enum": [t.value for t in EntityType]},
                    "description": {"type": "string"},
                },
                "required": ["name", "type", "description"],
            },
        },
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "statement": {"type": "string"},
                    "entities": {"type": "array", "items": {"type": "string"}},
                    "polarity": {"type": "string", "enum": ["asserts", "disputes"]},
                    "excerpt": {"type": "string"},
                },
                "required": ["statement", "entities", "polarity", "excerpt"],
            },
        },
        "relationships": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "subject": {"type": "string"},
                    "predicate": {"type": "string",
                                  "enum": [p.value for p in Predicate]},
                    "object": {"type": "string"},
                },
                "required": ["subject", "predicate", "object"],
            },
        },
    },
    "required": ["entities", "claims", "relationships"],
}

_EXTRACT_SYSTEM = """You are the evidence-extraction module of a research engine.
From the document below, extract ONLY what the text itself supports:
- entities: concrete named things (technologies, companies, people, papers, products, concepts)
- claims: specific factual statements the document makes, each tied to entity names from your list;
  polarity "asserts" if stated as true, "disputes" if the document argues against it;
  excerpt = the exact fragment of the document supporting the claim
- relationships: subject/predicate/object between your extracted entities

Rules: no outside knowledge, no speculation, no filler entities. If the
document supports nothing, return empty arrays. Extraction emphasis: {emphasis}"""


class EvidenceExtractor:
    def __init__(self, llm: LLMClient):
        self.llm = llm
        self.degraded = False  # flips true if any doc fell back to metadata-only

    # -- deterministic pieces --------------------------------------------
    def _evidence_for(self, doc: RawDoc, prior: float, excerpt: str) -> Evidence:
        """Provenance is built HERE from the fetched document, never by the LLM."""
        return Evidence(
            source=doc.source, category=doc.category, url=doc.url,
            title=doc.title, excerpt=excerpt[:500],
            authors=doc.authors, published=doc.published,
            reliability=score_reliability(doc, prior),
        )

    def _metadata_only(self, doc: RawDoc, prior: float) -> ExtractionResult:
        """LLM-free fallback: the document is itself an entity; no claims are invented."""
        self.degraded = True
        etype = EntityType.PAPER if doc.category.value == "academic" else EntityType.OTHER
        ent = Entity(name=doc.title[:200] or doc.url, type=etype,
                     description=doc.text[:300])
        return ExtractionResult(doc_url=doc.url, entities=[ent])

    # -- main entry point -------------------------------------------------
    async def extract(self, doc: RawDoc, prior: float,
                      emphasis: str = "") -> ExtractionResult:
        if not doc.text.strip() and not doc.title.strip():
            return ExtractionResult(doc_url=doc.url, rejected=1)

        body = (f"TITLE: {doc.title}\nSOURCE: {doc.source}\n"
                f"DATE: {doc.published.date() if doc.published else 'unknown'}\n"
                f"TEXT:\n{doc.text[:5000]}")
        try:
            proposal = await self.llm.chat_json(
                "extract", _EXTRACT_SYSTEM.format(emphasis=emphasis or "general"),
                body, _EXTRACT_SCHEMA)
        except LLMUnavailable:
            return self._metadata_only(doc, prior)

        # ---- the gate ---------------------------------------------------
        rejected = 0
        entities: dict[str, Entity] = {}  # keyed by lowercased proposed name
        for e in proposal.get("entities", []) or []:
            name = (e.get("name") or "").strip() if isinstance(e, dict) else ""
            if not name or len(name) > 200:
                rejected += 1
                continue
            try:
                etype = EntityType(e.get("type", "other"))
            except ValueError:
                etype = EntityType.OTHER
            entities[name.casefold()] = Entity(
                name=name, type=etype,
                description=(e.get("description") or "")[:400])

        claims: list[Claim] = []
        for c in proposal.get("claims", []) or []:
            if not isinstance(c, dict):
                rejected += 1
                continue
            statement = (c.get("statement") or "").strip()
            linked = [entities[n.casefold()].id
                      for n in (c.get("entities") or [])
                      if isinstance(n, str) and n.casefold() in entities]
            if not statement or not linked:
                rejected += 1  # claims must bind to extracted entities
                continue
            polarity = (Polarity.DISPUTES if c.get("polarity") == "disputes"
                        else Polarity.ASSERTS)
            ev = self._evidence_for(doc, prior, c.get("excerpt") or statement)
            claims.append(Claim(statement=statement[:600], entity_ids=linked,
                                polarity=polarity, evidence=[ev],
                                confidence=ev.reliability))

        relationships: list[Relationship] = []
        for r in proposal.get("relationships", []) or []:
            if not isinstance(r, dict):
                rejected += 1
                continue
            subj = entities.get((r.get("subject") or "").casefold())
            obj = entities.get((r.get("object") or "").casefold())
            try:
                pred = Predicate(r.get("predicate", ""))
            except ValueError:
                pred = None
            if subj is None or obj is None or pred is None or subj.id == obj.id:
                rejected += 1  # endpoints must exist; no self-loops
                continue
            ev = self._evidence_for(doc, prior, f"{subj.name} {pred.value} {obj.name}")
            relationships.append(Relationship(
                subject_id=subj.id, predicate=pred, object_id=obj.id,
                evidence_ids=[ev.id], confidence=ev.reliability))
            # relationship evidence rides along on a synthetic claim so the
            # ledger keeps one uniform evidence store
            claims.append(Claim(
                statement=f"{subj.name} {pred.value.replace('_', ' ')} {obj.name}",
                entity_ids=[subj.id, obj.id], evidence=[ev],
                confidence=ev.reliability))

        return ExtractionResult(doc_url=doc.url, entities=list(entities.values()),
                                claims=claims, relationships=relationships,
                                rejected=rejected)
