"""Phases 3 + 7 — the Software Context Graph: the system's working model.

One typed multigraph holds WHAT/WHY/HOW:

  node kinds: requirement, feature, component, file, test, api, entity,
              evidence, decision, problem, doc
  edge kinds: satisfied_by (req→feat), implemented_by (feat→cmp),
              materialized_in (cmp→file), exposes (cmp→api),
              touches (api→entity), owns (cmp→entity),
              depends_on (cmp→cmp), verifies (test→feat),
              informed_by (cmp→evidence), shaped_by (cmp→decision),
              documents (doc→cmp), afflicts (problem→node)

The graph is built BY CONSTRUCTION during generation — the generator calls
these methods as it writes each artifact, so provenance is never inferred
after the fact. It persists as a sidecar inside the generated repository
(.code_engine/graph.json): the software ships carrying its own self-model,
and impact analysis / evolution reload it from there.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import networkx as nx

from ..models import (Architecture, CheckResult, ResearchEvidence,
                      SoftwareSpec, now_utc)

# The sidecar directory inside a GENERATED project. This is an on-disk
# format name, not a module path: every project this engine has already
# written carries `.code_engine/`, and renaming it here would make those
# projects unreadable to the impact and evolve commands.
SIDECAR_REL = ".code_engine/graph.json"


class SoftwareContextGraph:
    def __init__(self, project_id: str):
        self.project_id = project_id
        self.g = nx.MultiDiGraph()

    # ------------------------------------------------------------------ #
    # construction API (called by the generator as it works)
    # ------------------------------------------------------------------ #
    def _node(self, node_id: str, kind: str, label: str, **props) -> str:
        if self.g.has_node(node_id):
            self.g.nodes[node_id].update(props)
        else:
            self.g.add_node(node_id, kind=kind, label=label[:160], **props)
        return node_id

    def _edge(self, src: str, dst: str, kind: str, **props) -> None:
        if not self.g.has_edge(src, dst, key=kind):
            self.g.add_edge(src, dst, key=kind, kind=kind, **props)

    def load_spec(self, spec: SoftwareSpec) -> None:
        self._node("project", "project", spec.product_name,
                   purpose=spec.purpose, request=spec.raw_request[:300])
        for req in spec.requirements:
            self._node(req.id, "requirement", req.text,
                       req_kind=req.kind, priority=req.priority.value)
            self._edge("project", req.id, "requires")

    def load_architecture(self, arch: Architecture) -> None:
        for feat in arch.features:
            self._node(feat.id, "feature", feat.name, description=feat.description)
            for rid in feat.requirement_ids:
                self._edge(rid, feat.id, "satisfied_by")
        for ent in arch.entities:
            self._node(f"entity:{ent.name}", "entity", ent.name,
                       fields=[f.name for f in ent.fields])
        for cmp in arch.components:
            cid = f"component:{cmp.name}"
            self._node(cid, "component", cmp.name, purpose=cmp.purpose,
                       cmp_kind=cmp.kind)
            for fid in cmp.feature_ids:
                self._edge(fid, cid, "implemented_by")
            for dep in cmp.depends_on:
                self._edge(cid, f"component:{dep}", "depends_on")
            for ent_name in cmp.entities:
                self._edge(cid, f"entity:{ent_name}", "owns")
            for ep in cmp.endpoints:
                api_id = f"api:{ep.method} {ep.path}"
                self._node(api_id, "api", f"{ep.method} {ep.path}",
                           summary=ep.summary, action=ep.action)
                self._edge(cid, api_id, "exposes")
                if ep.entity:
                    self._edge(api_id, f"entity:{ep.entity}", "touches")
        for adr in arch.decisions:
            self._node(adr.id, "decision", adr.title,
                       decision=adr.decision, rationale=adr.rationale)
            for name in adr.component_names:
                self._edge(f"component:{name}", adr.id, "shaped_by")

    def add_evidence(self, ev: ResearchEvidence,
                     component_names: list[str] | None = None) -> None:
        self._node(ev.id, "evidence", ev.title, agent=ev.agent,
                   topic=ev.topic, url=ev.url)
        for name in component_names or []:
            self._edge(f"component:{name}", ev.id, "informed_by")

    def add_file(self, path: str, component: str, role: str) -> None:
        """Every written file registers here — provenance by construction."""
        self._node(f"file:{path}", "file", path, role=role)
        self._edge(f"component:{component}", f"file:{path}", "materialized_in")

    def add_test(self, path: str, test_name: str, feature_id: str,
                 component: str) -> None:
        tid = f"test:{path}::{test_name}"
        self._node(tid, "test", test_name, path=path)
        if feature_id:  # a component may carry no mapped feature; no ghost edges
            self._edge(tid, feature_id, "verifies")
        self._edge(f"component:{component}", tid, "materialized_in")

    def add_doc(self, path: str, component_names: list[str]) -> None:
        self._node(f"doc:{path}", "doc", path)
        for name in component_names:
            self._edge(f"doc:{path}", f"component:{name}", "documents")

    def add_problem(self, message: str, subject_id: str | None = None,
                    source: str = "verification") -> str:
        pid = f"problem:{abs(hash(message)) % 10**10}"
        self._node(pid, "problem", message[:160], source=source,
                   recorded_at=now_utc().isoformat())
        if subject_id and self.g.has_node(subject_id):
            self._edge(pid, subject_id, "afflicts")
        return pid

    def record_verification(self, results: list[CheckResult]) -> None:
        for res in results:
            for failure in res.failures:
                subject = None
                if failure.get("component"):
                    subject = f"component:{failure['component']}"
                elif failure.get("file"):
                    subject = f"file:{failure['file']}"
                self.add_problem(
                    f"[{res.check}] {failure.get('message', '')[:120]}", subject)

    # ------------------------------------------------------------------ #
    # traversal helpers (impact analysis + agents read through these)
    # ------------------------------------------------------------------ #
    def nodes_of_kind(self, kind: str) -> list[tuple[str, dict]]:
        return [(n, d) for n, d in self.g.nodes(data=True) if d.get("kind") == kind]

    def out_edges(self, node_id: str, kind: str | None = None):
        for _u, v, k, d in self.g.out_edges(node_id, keys=True, data=True):
            if kind is None or k == kind:
                yield v, d

    def in_edges(self, node_id: str, kind: str | None = None):
        for u, _v, k, d in self.g.in_edges(node_id, keys=True, data=True):
            if kind is None or k == kind:
                yield u, d

    def component_of_file(self, path: str) -> str | None:
        for u, _d in self.in_edges(f"file:{path}", "materialized_in"):
            if u.startswith("component:"):
                return u.removeprefix("component:")
        return None

    def features_of_component(self, name: str) -> list[str]:
        return [u for u, _d in self.in_edges(f"component:{name}", "implemented_by")]

    def tests_verifying_feature(self, feature_id: str) -> list[str]:
        return [u for u, _d in self.in_edges(feature_id, "verifies")]

    def stats(self) -> dict:
        kinds: dict[str, int] = defaultdict(int)
        for _n, d in self.g.nodes(data=True):
            kinds[d.get("kind", "?")] += 1
        return {"nodes": dict(kinds), "edges": self.g.number_of_edges()}

    # ------------------------------------------------------------------ #
    # persistence: the sidecar inside the generated repository
    # ------------------------------------------------------------------ #
    def save_sidecar(self, repo_root: Path) -> Path:
        path = repo_root / SIDECAR_REL
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "project_id": self.project_id,
            "saved_at": now_utc().isoformat(),
            "nodes": [{"id": n, "props": dict(d)} for n, d in self.g.nodes(data=True)],
            "edges": [{"src": u, "dst": v, "kind": k, "props": dict(d)}
                      for u, v, k, d in self.g.edges(keys=True, data=True)],
        }
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=1, default=str))
        tmp.replace(path)
        return path

    @classmethod
    def load_sidecar(cls, repo_root: Path) -> "SoftwareContextGraph":
        data = json.loads((repo_root / SIDECAR_REL).read_text())
        cg = cls(data["project_id"])
        for n in data["nodes"]:
            cg.g.add_node(n["id"], **n["props"])
        for e in data["edges"]:
            cg.g.add_edge(e["src"], e["dst"], key=e["kind"], **e["props"])
        return cg
