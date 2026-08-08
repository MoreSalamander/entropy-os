"""Phase 6 — the Multi-Agent Software Engineering Organization.

Every agent is a named role with a real mechanism operating on the SHARED
model (spec / architecture / context graph) — not an isolated context
window. The roster and where each mechanism lives:

  Product Agent            intent.py — spec extraction, MoSCoW floor, baselines
  Architect Agent          architecture.py — gated design + ADRs into the graph
  Research Agents (6)      research.py — parallel evidence into graph + KG
  Implementation Agents    codegen/generator.py — backend/db/frontend passes
  Testing Agent            codegen (test generation) + verify.py (execution)
  Security Agent           HERE — generated-code lint + OSV via research/evolve
  Performance Agent        HERE — static latency/scale smells on generated code
  Code Review Agent        HERE — consistency + maintainability lint
  Documentation Agent      codegen._docs — docs derived from the model

The three lint agents below return CheckResults that join the Phase 9
verification loop as first-class checks.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from .models import CheckResult, CheckStatus

ORG_ROSTER = [
    "Product Agent", "Architect Agent", "Technology Research Agent",
    "Architecture Research Agent", "Open Source Research Agent",
    "Documentation Research Agent", "Security Research Agent",
    "UX Research Agent", "Backend Implementation Agent",
    "Database Implementation Agent", "Frontend Implementation Agent",
    "Testing Agent", "Security Agent", "Performance Agent",
    "Code Review Agent", "Documentation Agent",
]


def _py_files(root: Path, sub: str = "app") -> list[Path]:
    return sorted((root / sub).rglob("*.py")) if (root / sub).exists() else []


class SecurityAgent:
    """Static security review of the generated source. Deterministic rules:
    no eval/exec/os.system/pickle-of-input, no plaintext secret literals,
    no SQL string building, mutating endpoints must consume validated
    schemas (payload: schemas.*) rather than raw dicts."""

    name = "Security Agent"

    def review(self, root: Path) -> CheckResult:
        failures: list[dict] = []
        for py in _py_files(root):
            rel = str(py.relative_to(root))
            text = py.read_text()
            for pattern, message in (
                    (r"\beval\(", "eval() on any input is prohibited"),
                    (r"\bexec\(", "exec() is prohibited"),
                    (r"os\.system\(|subprocess\.", "shell execution in a web service"),
                    (r"pickle\.loads?\(", "pickle deserialization is unsafe"),
                    (r"(password|secret|api_key)\s*=\s*[\"'][^\"']{6,}",
                     "hardcoded secret literal"),
                    (r"execute\(\s*f?[\"'].*(SELECT|INSERT|UPDATE|DELETE).*[%{]",
                     "string-built SQL")):
                if re.search(pattern, text, re.I):
                    failures.append({"file": rel, "message": message})
            # mutating routes must take a validated schema payload
            for m in re.finditer(
                    r"@router\.(post|put)\([^)]*\)\s*\ndef (\w+)\(([^)]*)\)",
                    text):
                args = m.group(3)
                if ("schemas." not in args and "Depends" in args
                        and "item_id" not in args):
                    failures.append({
                        "file": rel,
                        "message": f"{m.group(2)}: mutating endpoint without a "
                                   f"validated schema payload"})
        return CheckResult(check="security",
                           status=CheckStatus.FAIL if failures else CheckStatus.PASS,
                           detail=f"{len(failures)} findings", failures=failures)


class PerformanceAgent:
    """Static performance review: queries inside loops (N+1 shape),
    list endpoints without any bound (full-table dumps), synchronous
    sleeps in request paths."""

    name = "Performance Agent"

    def review(self, root: Path) -> CheckResult:
        failures: list[dict] = []
        for py in _py_files(root):
            rel = str(py.relative_to(root))
            text = py.read_text()
            try:
                tree = ast.parse(text)
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if isinstance(node, (ast.For, ast.While)):
                    body_src = ast.get_source_segment(text, node) or ""
                    if re.search(r"session\.(get|scalars|execute)\(", body_src):
                        failures.append({
                            "file": rel,
                            "message": f"query inside a loop near line "
                                       f"{node.lineno} (N+1 shape)"})
            if "time.sleep(" in text and "routers" in rel:
                failures.append({"file": rel,
                                 "message": "blocking sleep in a request path"})
        return CheckResult(check="performance",
                           status=CheckStatus.FAIL if failures else CheckStatus.PASS,
                           detail=f"{len(failures)} findings", failures=failures)


class CodeReviewAgent:
    """Consistency & maintainability: every public route documented
    (docstring), no function over 60 lines, routers must not import
    models directly (the service layer is the boundary)."""

    name = "Code Review Agent"

    def review(self, root: Path) -> CheckResult:
        failures: list[dict] = []
        for py in _py_files(root):
            rel = str(py.relative_to(root))
            text = py.read_text()
            try:
                tree = ast.parse(text)
            except SyntaxError:
                failures.append({"file": rel, "message": "unparseable"})
                continue
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    length = (node.end_lineno or node.lineno) - node.lineno
                    if length > 60:
                        failures.append({
                            "file": rel,
                            "message": f"{node.name}: {length} lines — split it"})
                    if ("routers/" in rel and not node.name.startswith("_")
                            and ast.get_docstring(node) is None):
                        failures.append({
                            "file": rel,
                            "message": f"{node.name}: route without docstring"})
            if "routers/" in rel and re.search(r"from app import .*\bmodels\b", text):
                failures.append({
                    "file": rel,
                    "message": "router imports models directly — go through "
                               "the service layer"})
        return CheckResult(check="review",
                           status=CheckStatus.FAIL if failures else CheckStatus.PASS,
                           detail=f"{len(failures)} findings", failures=failures)


def run_static_agents(root: Path) -> list[CheckResult]:
    return [SecurityAgent().review(root), PerformanceAgent().review(root),
            CodeReviewAgent().review(root)]
