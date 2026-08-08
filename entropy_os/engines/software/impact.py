"""Phase 10 — Change Impact Analysis: pure graph traversal, no guessing.

Given a component, walk the Context Graph and report everything a change
would touch BEFORE anyone edits code:

  dependents      components with depends_on edges into the target
                  (transitive — a change ripples)
  APIs            endpoints the target and its dependents expose
  tests           tests verifying features implemented by any affected
                  component
  requirements    requirements those features satisfy
  docs            documentation nodes documenting affected components
  files           materialized files of affected components
  infra           Dockerfile/config files (flagged when the target is the
                  database or any component with entities — schema changes
                  reach deployment)
"""

from __future__ import annotations

from .graphs.context_graph import SoftwareContextGraph
from .models import ImpactReport


def analyze_impact(cg: SoftwareContextGraph, component: str) -> ImpactReport:
    target = f"component:{component}"
    if not cg.g.has_node(target):
        raise KeyError(f"unknown component: {component}")

    # transitive dependents (who depends on the target, directly or through others)
    dependents: set[str] = set()
    frontier = [target]
    while frontier:
        node = frontier.pop()
        for u, _d in cg.in_edges(node, "depends_on"):
            if u not in dependents and u != target:
                dependents.add(u)
                frontier.append(u)
    affected_components = [target] + sorted(dependents)

    apis: list[str] = []
    files: list[str] = []
    features: set[str] = set()
    for cid in affected_components:
        for v, _d in cg.out_edges(cid, "exposes"):
            apis.append(v.removeprefix("api:"))
        for v, _d in cg.out_edges(cid, "materialized_in"):
            if v.startswith("file:"):
                files.append(v.removeprefix("file:"))
        for u, _d in cg.in_edges(cid, "implemented_by"):
            features.add(u)

    tests: set[str] = set()
    requirements: set[str] = set()
    for feat in features:
        for t in cg.tests_verifying_feature(feat):
            props = cg.g.nodes.get(t, {})
            tests.add(f"{props.get('path', '?')}::{props.get('label', t)}")
        for u, _d in cg.in_edges(feat, "satisfied_by"):
            props = cg.g.nodes.get(u, {})
            requirements.add(props.get("label", u))

    docs: set[str] = set()
    for cid in affected_components:
        for u, _d in cg.in_edges(cid, "documents"):
            docs.add(u.removeprefix("doc:"))

    infra: list[str] = []
    target_props = cg.g.nodes.get(target, {})
    owns_entities = any(True for _v, _d in cg.out_edges(target, "owns"))
    if component == "database" or owns_entities or target_props.get("cmp_kind") == "store":
        infra = ["Dockerfile (image rebuild)",
                 "DATABASE_URL consumers (schema change reaches deployment)"]

    return ImpactReport(
        target=component,
        dependent_components=[c.removeprefix("component:")
                              for c in affected_components[1:]],
        affected_apis=sorted(set(apis)),
        affected_tests=sorted(tests),
        affected_requirements=sorted(requirements),
        stale_docs=sorted(docs),
        affected_files=sorted(set(files)),
        infra_touchpoints=infra,
    )


def impact_markdown(report: ImpactReport) -> str:
    lines = [f"# Change impact: `{report.target}`", ""]
    sections = [
        ("Dependent components (transitive)", report.dependent_components),
        ("Affected APIs", report.affected_apis),
        ("Tests to re-run / update", report.affected_tests),
        ("Requirements potentially affected", report.affected_requirements),
        ("Documentation now suspect", report.stale_docs),
        ("Files in scope", report.affected_files),
        ("Infrastructure touchpoints", report.infra_touchpoints),
    ]
    for title, rows in sections:
        lines.append(f"## {title}")
        lines += [f"- {r}" for r in rows] or ["- (none)"]
        lines.append("")
    return "\n".join(lines)
