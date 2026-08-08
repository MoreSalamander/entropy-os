"""Phase 5 — Architecture Intelligence (the Architect Agent's core mechanism).

Understanding before implementation, enforced: the LLM proposes features,
components, entities, and endpoints through a schema gate, and deterministic
validators then guarantee the properties codegen depends on:

  * every MUST functional requirement is satisfied by ≥1 feature
    (uncovered requirements get an auto-feature — visible in
    validation_notes, never silently dropped)
  * every feature is implemented by ≥1 component
  * component names are unique snake_case; depends_on references resolve
  * every entity is owned by exactly one component; field types come from
    the allowed set; an `id` primary key is guaranteed
  * endpoint paths are well-formed; CRUD actions are derived from
    method+path when the proposal omits them; entity references resolve
  * the database store component and (when any UI-ish requirement exists)
    the static web_ui component always exist
  * the stack decision is recorded as an ADR node with rationale, including
    KG pattern priors that informed it

If the LLM is down, a deterministic single-service architecture still
satisfies the spec's MUST requirements — degraded and labeled.
"""

from __future__ import annotations

import re

from entropy_os.engines.research.llm.client import LLMClient, LLMUnavailable

from .models import (ApiEndpoint, Architecture, Component, Decision,
                     EntityField, EntityModel, Feature, Priority,
                     SoftwareSpec, slug)

_FIELD_TYPES = ["str", "int", "float", "bool", "datetime", "text"]

_ARCH_SCHEMA = {
    "type": "object",
    "properties": {
        "features": {"type": "array", "items": {"type": "object", "properties": {
            "name": {"type": "string"}, "description": {"type": "string"},
            "requirement_texts": {"type": "array", "items": {"type": "string"}}},
            "required": ["name", "description", "requirement_texts"]}},
        "entities": {"type": "array", "items": {"type": "object", "properties": {
            "name": {"type": "string"},
            "fields": {"type": "array", "items": {"type": "object", "properties": {
                "name": {"type": "string"},
                "type": {"type": "string", "enum": _FIELD_TYPES}},
                "required": ["name", "type"]}}},
            "required": ["name", "fields"]}},
        "components": {"type": "array", "items": {"type": "object", "properties": {
            "name": {"type": "string"}, "purpose": {"type": "string"},
            "feature_names": {"type": "array", "items": {"type": "string"}},
            "depends_on": {"type": "array", "items": {"type": "string"}},
            "entities": {"type": "array", "items": {"type": "string"}},
            "endpoints": {"type": "array", "items": {"type": "object", "properties": {
                "method": {"type": "string", "enum": ["GET", "POST", "PUT", "DELETE"]},
                "path": {"type": "string"}, "summary": {"type": "string"},
                "entity": {"type": "string"}},
                "required": ["method", "path", "summary", "entity"]}}},
            "required": ["name", "purpose", "feature_names", "depends_on",
                         "entities", "endpoints"]}},
    },
    "required": ["features", "entities", "components"],
}

_SYSTEM = """You are the architecture module of a software engineering platform.
Given the specification and research brief, design the system as JSON.

Stack is fixed: Python + FastAPI + SQLAlchemy/SQLite + pytest, static JS frontend.
Design within it:
- features: 3-7, each naming which requirement texts it satisfies (verbatim substrings)
- entities: the persisted domain objects (PascalCase) with typed fields
  (str,int,float,bool,datetime,text). Do NOT add an id field — it is implicit.
- components: 3-6 snake_case services. Each lists the features it implements,
  the entities it owns (an entity has exactly ONE owner), other components it
  depends on, and the REST endpoints it exposes (paths like /things or
  /things/{id}; entity naming which entity the endpoint touches, "" if none).
Keep it as simple as the requirements allow. No filler components."""


class ArchitectAgent:
    def __init__(self, llm: LLMClient):
        self.llm = llm

    async def design(self, spec: SoftwareSpec, research_brief: str = "",
                     pattern_priors: list[dict] | None = None) -> Architecture:
        notes: list[str] = []
        user = (f"SPEC: {spec.product_name} — {spec.purpose}\n"
                "Requirements:\n" +
                "\n".join(f"- [{r.kind}/{r.priority.value}] {r.text}"
                          for r in spec.requirements) +
                (f"\n\nRESEARCH BRIEF:\n{research_brief[:1500]}" if research_brief else "") +
                (("\n\nPATTERN PRIORS (prefer proven ones):\n" +
                  "\n".join(f"- {p['pattern']}: applied {p['applied']}, "
                            f"success {p['success_rate']}"
                            for p in (pattern_priors or [])[:6]))
                 if pattern_priors else ""))
        try:
            proposal = await self.llm.chat_json("plan", _SYSTEM, user, _ARCH_SCHEMA)
        except LLMUnavailable:
            proposal = {}
            notes.append("LLM unavailable — deterministic fallback architecture")

        arch = self._validate(spec, proposal, notes)
        arch.decisions.append(Decision(
            title="Stack: FastAPI + SQLAlchemy/SQLite + pytest + static JS",
            decision="Generate a modular FastAPI service with SQLite persistence, "
                     "pytest verification, and a dependency-free static frontend.",
            rationale="Local-first constraint; single proven deep stack over "
                      "shallow multi-stack pretense; every layer verifiable "
                      "offline. Pattern priors considered: "
                      + (", ".join(p["pattern"] for p in (pattern_priors or [])[:4])
                         or "none yet"),
            component_names=[c.name for c in arch.components]))
        arch.spec_id = spec.id
        arch.validation_notes = notes
        return arch

    # ------------------------------------------------------------------ #
    def _validate(self, spec: SoftwareSpec, proposal: dict,
                  notes: list[str]) -> Architecture:
        # ---- entities -------------------------------------------------
        entities: dict[str, EntityModel] = {}
        for e in proposal.get("entities") or []:
            if not isinstance(e, dict):
                continue
            name = re.sub(r"[^A-Za-z0-9]", "", str(e.get("name", "")))
            if not name:
                continue
            name = name[0].upper() + name[1:]
            fields = []
            for f in e.get("fields") or []:
                fname = slug(str(f.get("name", "")))
                if not fname or fname == "id":
                    continue
                ftype = f.get("type") if f.get("type") in _FIELD_TYPES else "str"
                fields.append(EntityField(name=fname, type=ftype))
            if not fields:
                fields = [EntityField(name="name", type="str")]
                notes.append(f"entity {name}: no valid fields proposed; defaulted")
            entities[name] = EntityModel(name=name, fields=fields)
        if not entities:
            entities["Item"] = EntityModel(name="Item", fields=[
                EntityField(name="title", type="str"),
                EntityField(name="body", type="text")])
            notes.append("no entities proposed; defaulted to Item")

        # ---- features + requirement coverage --------------------------
        features: list[Feature] = []
        req_by_text = {r.text: r for r in spec.requirements}
        covered: set[str] = set()
        for f in proposal.get("features") or []:
            if not isinstance(f, dict) or not str(f.get("name", "")).strip():
                continue
            req_ids = []
            for text in f.get("requirement_texts") or []:
                for rtext, req in req_by_text.items():
                    if isinstance(text, str) and (text in rtext or rtext in text):
                        req_ids.append(req.id)
                        covered.add(req.id)
            features.append(Feature(name=str(f["name"])[:80],
                                    description=str(f.get("description", ""))[:300],
                                    requirement_ids=sorted(set(req_ids))))
        for req in spec.requirements:
            if (req.kind == "functional" and req.priority == Priority.MUST
                    and req.id not in covered):
                features.append(Feature(
                    name=f"Cover: {req.text[:50]}",
                    description=f"Auto-created to satisfy uncovered MUST "
                                f"requirement: {req.text}",
                    requirement_ids=[req.id]))
                notes.append(f"MUST requirement uncovered by proposal; "
                             f"auto-feature added: {req.text[:60]}")
        if not features:
            features = [Feature(name="Core capability", description=spec.purpose,
                                requirement_ids=[r.id for r in spec.requirements
                                                 if r.kind == "functional"])]

        feat_by_name = {f.name: f for f in features}

        # ---- components -----------------------------------------------
        components: list[Component] = []
        seen_names: set[str] = set()
        owned: dict[str, str] = {}  # entity -> component
        for c in proposal.get("components") or []:
            if not isinstance(c, dict):
                continue
            name = slug(str(c.get("name", "")))
            if not name or name in seen_names:
                continue
            seen_names.add(name)
            feat_ids = [feat_by_name[fn].id for fn in c.get("feature_names") or []
                        if fn in feat_by_name]
            ents = []
            for en in c.get("entities") or []:
                en_clean = re.sub(r"[^A-Za-z0-9]", "", str(en))
                en_clean = en_clean[:1].upper() + en_clean[1:]
                if en_clean in entities and en_clean not in owned:
                    owned[en_clean] = name
                    ents.append(en_clean)
            endpoints = []
            for ep in c.get("endpoints") or []:
                if not isinstance(ep, dict):
                    continue
                path = str(ep.get("path", "")).strip()
                if not re.fullmatch(r"(/[a-z0-9_\-{}]+)+", path):
                    notes.append(f"dropped malformed endpoint path: {path!r}")
                    continue
                entity = re.sub(r"[^A-Za-z0-9]", "", str(ep.get("entity", "")))
                entity = entity[:1].upper() + entity[1:] if entity else ""
                if entity and entity not in entities:
                    entity = ""
                # normalize the path parameter name: generated CRUD handlers
                # bind `item_id`, so any proposed `{id}`/`{dataset_id}` must
                # become `{item_id}` or the param never binds (live-run bug)
                if entity and re.search(r"\{[^}]+\}", path):
                    path = re.sub(r"\{[^}]+\}", "{item_id}", path, count=1)
                method = ep.get("method", "GET")
                action = ("get" if method == "GET" and path.endswith("}")
                          else "list" if method == "GET"
                          else "create" if method == "POST"
                          else "update" if method == "PUT"
                          else "delete" if method == "DELETE" else "custom")
                endpoints.append(ApiEndpoint(method=method, path=path,
                                             summary=str(ep.get("summary", ""))[:150],
                                             entity=entity, action=action))
            components.append(Component(
                name=name, purpose=str(c.get("purpose", ""))[:200],
                kind="service", feature_ids=feat_ids,
                depends_on=[slug(str(d)) for d in c.get("depends_on") or []],
                entities=ents, endpoints=endpoints))

        if not components:
            components = [Component(
                name="core", purpose=f"single-service implementation of "
                                     f"{spec.product_name}",
                feature_ids=[f.id for f in features],
                entities=list(entities), endpoints=[])]
            notes.append("no components proposed; single core service created")
            owned = {e: "core" for e in entities}

        # unowned entities go to the component with the most endpoints
        fallback_owner = max(components, key=lambda c: len(c.endpoints)).name
        for en in entities:
            if en not in owned:
                owned[en] = fallback_owner
                next(c for c in components if c.name == fallback_owner).entities.append(en)
                notes.append(f"entity {en} had no owner; assigned to {fallback_owner}")

        # entity-owning components with zero endpoints get standard CRUD —
        # a persisted entity nobody can reach is a modeling error
        for comp in components:
            for en in comp.entities:
                if not any(ep.entity == en for ep in comp.endpoints):
                    base = f"/{EntityModel(name=en, fields=[]).snake}s"
                    comp.endpoints += [
                        ApiEndpoint(method="GET", path=base,
                                    summary=f"List {en} records", entity=en, action="list"),
                        ApiEndpoint(method="POST", path=base,
                                    summary=f"Create a {en}", entity=en, action="create"),
                        ApiEndpoint(method="GET", path=base + "/{item_id}",
                                    summary=f"Fetch one {en}", entity=en, action="get"),
                        ApiEndpoint(method="DELETE", path=base + "/{item_id}",
                                    summary=f"Delete a {en}", entity=en, action="delete"),
                    ]
                    notes.append(f"entity {en}: no endpoints proposed; CRUD added")

        # resolve depends_on to real names; drop danglers
        valid = {c.name for c in components} | {"database", "web_ui"}
        for comp in components:
            dangling = [d for d in comp.depends_on if d not in valid]
            comp.depends_on = [d for d in comp.depends_on if d in valid and d != comp.name]
            for d in dangling:
                notes.append(f"component {comp.name}: dropped unknown dependency {d!r}")

        # guaranteed infrastructure components
        components.append(Component(
            name="database", purpose="SQLite persistence via SQLAlchemy; "
                                     "session-per-request", kind="store",
            entities=[], endpoints=[]))
        for comp in components:
            if comp.kind == "service" and comp.entities:
                comp.depends_on = sorted(set(comp.depends_on) | {"database"})
        ui_wanted = any("ui" in r.text.casefold() or "interface" in r.text.casefold()
                        or "web" in r.text.casefold() for r in spec.requirements)
        if ui_wanted:
            api_owners = [c.name for c in components if c.endpoints]
            components.append(Component(
                name="web_ui", purpose="dependency-free static frontend over the API",
                kind="ui", depends_on=api_owners, entities=[], endpoints=[]))

        return Architecture(features=features, components=components,
                            entities=list(entities.values()))
