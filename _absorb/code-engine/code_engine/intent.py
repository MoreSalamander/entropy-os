"""Phase 1 — Software Intent Analysis (the Product Agent's core mechanism).

User idea → structured SoftwareSpec through a schema gate, then deterministic
validation: every requirement typed and prioritized, at least one MUST
functional requirement (a product with none isn't buildable), nonfunctional/
security baselines injected if the proposal omitted them (tests, docs,
input validation are not optional in this house), workable fallback when
the LLM is down.
"""

from __future__ import annotations

from research_engine.llm.client import LLMClient, LLMUnavailable

from .models import Priority, Requirement, SoftwareSpec

_SPEC_SCHEMA = {
    "type": "object",
    "properties": {
        "product_name": {"type": "string"},
        "purpose": {"type": "string"},
        "user_types": {"type": "array", "items": {"type": "string"}},
        "requirements": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "kind": {"type": "string",
                         "enum": ["functional", "nonfunctional", "data",
                                  "security", "integration"]},
                "text": {"type": "string"},
                "priority": {"type": "string", "enum": ["must", "should", "could"]},
            },
            "required": ["kind", "text", "priority"]}},
        "technical_constraints": {"type": "array", "items": {"type": "string"}},
        "unknowns": {"type": "array", "items": {"type": "string"}},
        "dependencies": {"type": "array", "items": {"type": "string"}},
        "candidate_approaches": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["product_name", "purpose", "user_types", "requirements",
                 "technical_constraints", "unknowns", "dependencies",
                 "candidate_approaches"],
}

_SYSTEM = """You are the product-intelligence module of a software engineering platform.
From the user's idea, produce a structured software specification as JSON:
- product_name: short, concrete (invent a neutral one if absent)
- purpose: one sentence, specific
- user_types: 2-4 concrete user groups
- requirements: 6-14 items across kinds (functional first; include data,
  security, and nonfunctional needs), each with a MoSCoW priority.
  Functional requirements must describe capabilities, not implementation.
- technical_constraints: real constraints only (e.g. "runs locally", "no paid APIs")
- unknowns: genuinely open questions
- dependencies: external systems/services this product must talk to
- candidate_approaches: 2-4 architectural directions worth researching
Be concrete. No filler."""

# Baselines injected when a proposal omits them — this platform does not
# generate software without tests, docs, or input validation.
_BASELINES = [
    Requirement(kind="nonfunctional", text="Automated test suite covering every feature",
                priority=Priority.MUST),
    Requirement(kind="security", text="Validate and constrain all API inputs",
                priority=Priority.MUST),
    Requirement(kind="nonfunctional", text="Architecture and API documentation generated from the system model",
                priority=Priority.SHOULD),
]


class IntentAnalyzer:
    def __init__(self, llm: LLMClient):
        self.llm = llm

    async def analyze(self, request: str) -> SoftwareSpec:
        proposal: dict = {}
        try:
            proposal = await self.llm.chat_json(
                "plan", _SYSTEM, f"Software idea: {request}", _SPEC_SCHEMA)
        except LLMUnavailable:
            proposal = {}

        def _strs(key: str, fallback: list[str]) -> list[str]:
            vals = proposal.get(key)
            if not isinstance(vals, list):
                return fallback
            clean = [v.strip() for v in vals if isinstance(v, str) and v.strip()]
            return clean or fallback

        requirements: list[Requirement] = []
        for r in proposal.get("requirements") or []:
            if not isinstance(r, dict) or not str(r.get("text", "")).strip():
                continue
            kind = r.get("kind") if r.get("kind") in (
                "functional", "nonfunctional", "data", "security", "integration") \
                else "functional"
            try:
                prio = Priority(r.get("priority", "should"))
            except ValueError:
                prio = Priority.SHOULD
            requirements.append(Requirement(kind=kind, text=str(r["text"])[:300],
                                            priority=prio))

        # deterministic floor: a buildable spec needs MUST functional reqs
        if not any(r.kind == "functional" and r.priority == Priority.MUST
                   for r in requirements):
            requirements.insert(0, Requirement(
                kind="functional", priority=Priority.MUST,
                text=f"Provide the core capability described: {request[:200]}"))

        # inject missing baselines (match on rough text overlap, not equality)
        existing = " ".join(r.text.casefold() for r in requirements)
        for base in _BASELINES:
            probe = base.text.casefold().split()[1]  # "test", "validate", "architecture"
            if probe not in existing:
                requirements.append(base.model_copy())

        name = str(proposal.get("product_name") or "").strip()
        if not name:
            words = [w for w in request.split() if w[:1].isupper() or len(w) > 5]
            name = (words[0].strip(".,") if words else "Untitled").capitalize()

        return SoftwareSpec(
            raw_request=request,
            product_name=name[:40],
            purpose=str(proposal.get("purpose") or request)[:300],
            user_types=_strs("user_types", ["general users"]),
            requirements=requirements,
            technical_constraints=_strs("technical_constraints", ["runs locally"]),
            unknowns=_strs("unknowns", []),
            dependencies=_strs("dependencies", []),
            candidate_approaches=_strs("candidate_approaches",
                                       ["modular FastAPI service"]),
        )
