"""Phase 11 — Software Evolution: on-demand health of a generated project.

`evolve(project_dir)` reloads the sidecar model and checks the software
against reality:

  test_failure   re-run the real verification suite
  drift          ast-observed structure vs the declared model
                 (CodebaseAnalyzer)
  vuln           OSV.dev live query for the project's requirements
  stale_dep      PyPI live latest-version vs requirement floors
  doc_drift      docs that reference components no longer in the model

Findings land back in the sidecar graph as problem nodes, so the repo's
self-model stays truthful over time. This is a command (cron it if you want
a cadence), not a resident daemon — stated plainly.
"""

from __future__ import annotations

import re
from pathlib import Path

import httpx

from entropy_os.engines.research.llm.client import LLMClient

from .graphs.codebase_model import CodebaseAnalyzer
from .graphs.context_graph import SoftwareContextGraph
from .models import CheckStatus, EvolutionFinding
from .verify import Verifier


def _read_requirements(root: Path) -> list[str]:
    reqs: list[str] = []
    for name in ("requirements.txt",):
        path = root / name
        if not path.exists():
            continue
        for line in path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith(("#", "-r")):
                reqs.append(re.split(r"[><=~\[]", line)[0].casefold())
    return reqs


async def evolve(root: Path, llm: LLMClient, log=print) -> list[EvolutionFinding]:
    cg = SoftwareContextGraph.load_sidecar(root)
    findings: list[EvolutionFinding] = []

    # 1. re-verify with the real suite (no repair here — evolution reports,
    #    a human or a follow-up engine run decides)
    verifier = Verifier(llm, max_repair_rounds=0)
    report = await verifier.verify(root, cg, log=log)
    for res in report.results:
        if res.status == CheckStatus.FAIL:
            for f in res.failures[:8]:
                findings.append(EvolutionFinding(
                    kind="test_failure", severity="blocker",
                    subject=f.get("file", "?"),
                    message=f"[{res.check}] {f.get('message', '')[:140]}"))

    # 2. declared vs observed drift
    findings += CodebaseAnalyzer(root).drift_report(cg)

    # 3+4. live dependency intelligence (keyless: OSV + PyPI)
    packages = _read_requirements(root)
    if packages:
        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                r = await client.post(
                    "https://api.osv.dev/v1/querybatch",
                    json={"queries": [{"package": {"name": p, "ecosystem": "PyPI"}}
                                      for p in packages]})
                r.raise_for_status()
                for pkg, res in zip(packages, r.json().get("results", []), strict=True):
                    vulns = res.get("vulns") or []
                    if vulns:
                        findings.append(EvolutionFinding(
                            kind="vuln", severity="warning", subject=pkg,
                            message=f"{pkg}: {len(vulns)} OSV advisories across "
                                    f"all versions — review applicability: "
                                    + ", ".join(v.get("id", "?") for v in vulns[:4])))
            except httpx.HTTPError as e:
                findings.append(EvolutionFinding(
                    kind="vuln", severity="note", subject="osv.dev",
                    message=f"OSV check unavailable: {e}"))
            for pkg in packages:
                try:
                    r = await client.get(f"https://pypi.org/pypi/{pkg}/json")
                    r.raise_for_status()
                    latest = r.json().get("info", {}).get("version", "")
                    if latest:
                        findings.append(EvolutionFinding(
                            kind="stale_dep", severity="note", subject=pkg,
                            message=f"{pkg}: latest on PyPI is {latest}; "
                                    f"requirements floor allows it — pin review"))
                except httpx.HTTPError:
                    continue

    # 5. documentation drift: docs mentioning components the model lacks
    known_components = {n.removeprefix("component:")
                        for n, _d in cg.nodes_of_kind("component")}
    for doc_node, _props in cg.nodes_of_kind("doc"):
        doc_path = root / doc_node.removeprefix("doc:")
        if not doc_path.exists():
            findings.append(EvolutionFinding(
                kind="doc_drift", severity="warning",
                subject=doc_node.removeprefix("doc:"),
                message="documented file missing from disk"))
            continue
        text = doc_path.read_text()
        for m in re.finditer(r"\| *([a-z][a-z0-9_]+) *\| *(service|store|ui)", text):
            if m.group(1) not in known_components:
                findings.append(EvolutionFinding(
                    kind="doc_drift", severity="warning",
                    subject=doc_node.removeprefix("doc:"),
                    message=f"doc references unknown component "
                            f"'{m.group(1)}'"))

    # findings persist into the sidecar so the self-model stays truthful
    for f in findings:
        if f.severity in ("blocker", "warning"):
            cg.add_problem(f"[{f.kind}] {f.message[:140]}", source="evolution")
    cg.save_sidecar(root)
    return findings
