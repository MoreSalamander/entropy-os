"""Phases 4 + 12 — the Software Knowledge Graph: reusable engineering memory.

Built on research-engine's GraphStore + VectorIndex. Node kinds: technology,
pattern, project. Edge vocabulary (the spec's list, applied where each
relation is actually derivable): uses, depends_on, implements, compatible_with,
requires, secured_by, tested_by, optimized_for.

Cross-project learning is concrete: every generated project records which
named patterns it applied and how verification went; `pattern_priors()`
returns patterns ranked by observed success (verification pass rate, repair
rounds) for the architecture proposer to prefer. Technologies accumulate
real metadata from research (PyPI versions, OSV advisory counts) — the graph
learns from evidence and outcomes, never from invented telemetry.
"""

from __future__ import annotations

from entropy_os.engines.research.graphs.store import GraphStore
from entropy_os.engines.research.graphs.vector_index import VectorIndex
from entropy_os.engines.research.models import normalize_name, now_utc

from ..models import ProjectOutcome, ResearchEvidence

# Named patterns this engine can apply; codegen reports which it used.
KNOWN_PATTERNS = {
    "router_service_split": "FastAPI routers stay thin; logic lives in service modules",
    "session_per_request": "SQLAlchemy session created and closed per request dependency",
    "schema_in_schema_out": "Pydantic models validate every request and shape every response",
    "tests_per_feature": "each feature carries at least one generated pytest test",
    "sidecar_self_model": "the repo ships its own context graph sidecar",
    "static_frontend_over_api": "dependency-free static JS frontend consuming the JSON API",
}


class SoftwareKnowledgeGraph:
    def __init__(self, store: GraphStore, vectors: VectorIndex):
        self.store = store
        self.vectors = vectors
        for name, desc in KNOWN_PATTERNS.items():
            if self.store.get_node(f"pattern:{name}") is None:
                self.store.upsert_node(f"pattern:{name}",
                                       {"kind": "pattern", "name": name,
                                        "description": desc,
                                        "applied": 0, "verified_ok": 0,
                                        "repair_rounds_total": 0})

    # ------------------------------------------------------------------ #
    async def absorb_evidence(self, evidence: list[ResearchEvidence]) -> int:
        """Technology facts from research land as/on technology nodes."""
        absorbed = 0
        for ev in evidence:
            if ev.topic not in ("technology", "security"):
                continue
            pkg = ev.extra.get("package") or (
                ev.title.split()[0] if ev.topic == "technology" else "")
            if not pkg:
                continue
            node_id = f"technology:{normalize_name(pkg)}"
            existing = self.store.get_node(node_id) or {}
            props = {"kind": "technology", "name": pkg,
                     "last_seen": now_utc().isoformat()}
            if ev.extra.get("version"):
                props["latest_version"] = ev.extra["version"]
            if "advisories" in ev.extra:
                props["osv_advisories"] = ev.extra["advisories"]
            self.store.upsert_node(node_id, {**existing, **props})
            await self.vectors.upsert_entity(node_id, pkg, ev.summary or ev.title)
            absorbed += 1
        # baseline relations among the house stack (derivable, so declared)
        for src, kind, dst in (("fastapi", "depends_on", "pydantic"),
                               ("fastapi", "compatible_with", "sqlalchemy"),
                               ("sqlalchemy", "tested_by", "pytest"),
                               ("fastapi", "secured_by", "pydantic")):
            a, b = f"technology:{src}", f"technology:{dst}"
            if self.store.get_node(a) and self.store.get_node(b):
                self.store.upsert_edge(a, b, kind, {"source": "stack-baseline"})
        return absorbed

    # ------------------------------------------------------------------ #
    def record_outcome(self, outcome: ProjectOutcome) -> None:
        pid = f"project:{outcome.project_id}"
        self.store.upsert_node(pid, {
            "kind": "project", "name": outcome.product_name,
            "stack": outcome.stack, "components": outcome.components,
            "entities": outcome.entities, "endpoints": outcome.endpoints,
            "tests_generated": outcome.tests_generated,
            "verification_passed": outcome.verification_passed,
            "repair_rounds": outcome.repair_rounds,
            "created_at": outcome.created_at.isoformat(),
        })
        for pattern in outcome.patterns:
            node_id = f"pattern:{pattern}"
            props = self.store.get_node(node_id)
            if props is None:
                continue
            props["applied"] = int(props.get("applied", 0)) + 1
            props["verified_ok"] = (int(props.get("verified_ok", 0))
                                    + int(outcome.verification_passed))
            props["repair_rounds_total"] = (int(props.get("repair_rounds_total", 0))
                                            + outcome.repair_rounds)
            self.store.upsert_node(node_id, props)
            self.store.upsert_edge(pid, node_id, "uses", {})
        for tech in outcome.stack.values():
            tid = f"technology:{normalize_name(str(tech))}"
            if self.store.get_node(tid):
                self.store.upsert_edge(pid, tid, "uses", {})
        self.store.flush()

    def pattern_priors(self) -> list[dict]:
        """Patterns ranked by observed success — the Phase 12 reuse surface."""
        rows = []
        for _node_id, props in self.store.all_nodes():
            if props.get("kind") != "pattern":
                continue
            applied = int(props.get("applied", 0))
            ok = int(props.get("verified_ok", 0))
            rows.append({
                "pattern": props.get("name"),
                "description": props.get("description", ""),
                "applied": applied,
                "success_rate": round(ok / applied, 2) if applied else None,
                "avg_repair_rounds": (round(int(props.get("repair_rounds_total", 0))
                                            / applied, 2) if applied else None),
            })
        return sorted(rows, key=lambda r: (-(r["success_rate"] or 0),
                                           -r["applied"]))

    def technology_risk(self, name: str) -> dict | None:
        props = self.store.get_node(f"technology:{normalize_name(name)}")
        if props is None:
            return None
        return {"name": props.get("name"),
                "latest_version": props.get("latest_version"),
                "osv_advisories": props.get("osv_advisories", 0)}

    def stats(self) -> dict:
        kinds: dict[str, int] = {}
        for _n, props in self.store.all_nodes():
            kinds[props.get("kind", "?")] = kinds.get(props.get("kind", "?"), 0) + 1
        return {"nodes_by_kind": kinds, "edges": len(self.store.all_edges())}
