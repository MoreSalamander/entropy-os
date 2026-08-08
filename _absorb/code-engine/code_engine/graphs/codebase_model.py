"""Phase 7 (observed side) — the ast-based codebase analyzer.

The Context Graph declares what the software SHOULD be; this module reads
what it actually IS. Pure `ast` (no LLM): per Python file it extracts
imports, class and function definitions, and intra-project call/import
references, then rolls file-level facts up to component level using the
graph's file→component provenance.

Drift detection compares the two: a component importing another component's
modules without a declared depends_on edge, declared dependencies no code
exercises, files on disk the model doesn't know, and modeled files missing
from disk. Scope is honest: Python only, import/reference-level resolution
(not full call-graph inference).
"""

from __future__ import annotations

import ast
from pathlib import Path

from ..models import EvolutionFinding
from .context_graph import SoftwareContextGraph


class FileFacts:
    def __init__(self, path: str):
        self.path = path
        self.imports: set[str] = set()       # module dotted-paths
        self.defs: set[str] = set()          # class/function names defined
        self.parse_error: str = ""


class CodebaseAnalyzer:
    def __init__(self, repo_root: Path):
        self.root = repo_root

    # ------------------------------------------------------------------ #
    def analyze_file(self, rel_path: str) -> FileFacts:
        facts = FileFacts(rel_path)
        try:
            tree = ast.parse((self.root / rel_path).read_text())
        except (OSError, SyntaxError) as e:
            facts.parse_error = f"{type(e).__name__}: {e}"[:160]
            return facts
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                facts.imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                # level>0 (relative): resolve against the file's package
                if node.level:
                    pkg = rel_path.replace("/", ".").rsplit(".", 1)[0]
                    parts = pkg.split(".")[: len(pkg.split(".")) - node.level + 1]
                    base = ".".join(parts + [node.module])
                else:
                    base = node.module
                facts.imports.add(base)
                # `from pkg import name` may import a MODULE named `name` —
                # record the qualified form too, or cross-component imports
                # of sibling modules would be invisible to drift detection
                for alias in node.names:
                    facts.imports.add(f"{base}.{alias.name}")
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                facts.defs.add(node.name)
        return facts

    def analyze_repo(self) -> dict[str, FileFacts]:
        out: dict[str, FileFacts] = {}
        for py in sorted(self.root.rglob("*.py")):
            rel = str(py.relative_to(self.root))
            if any(part in (".venv", "node_modules", "__pycache__", ".code_engine")
                   for part in py.parts):
                continue
            out[rel] = self.analyze_file(rel)
        return out

    # ------------------------------------------------------------------ #
    def drift_report(self, cg: SoftwareContextGraph) -> list[EvolutionFinding]:
        """Declared model vs observed code. Every finding names its subject."""
        findings: list[EvolutionFinding] = []
        observed = self.analyze_repo()

        modeled_files = {n.removeprefix("file:")
                         for n, _d in cg.nodes_of_kind("file")
                         if n.removeprefix("file:").endswith(".py")}
        modeled_tests = {d.get("path", "") for _n, d in cg.nodes_of_kind("test")}

        # files on disk the model doesn't know / modeled files gone missing
        for rel in observed:
            if rel not in modeled_files and rel not in modeled_tests:
                findings.append(EvolutionFinding(
                    kind="drift", severity="warning", subject=rel,
                    message=f"file exists but is absent from the system model: {rel}"))
        for rel in modeled_files:
            if rel not in observed:
                findings.append(EvolutionFinding(
                    kind="drift", severity="blocker", subject=rel,
                    message=f"modeled file missing from disk: {rel}"))

        for rel, facts in observed.items():
            if facts.parse_error:
                findings.append(EvolutionFinding(
                    kind="drift", severity="blocker", subject=rel,
                    message=f"unparseable Python: {facts.parse_error}"))

        # component-level dependency drift: imports across components must
        # match declared depends_on edges
        comp_of_module: dict[str, str] = {}
        for rel in modeled_files:
            comp = cg.component_of_file(rel)
            if comp:
                comp_of_module[rel.replace("/", ".").removesuffix(".py")] = comp

        declared: dict[str, set[str]] = {}
        for cid, _d in cg.nodes_of_kind("component"):
            name = cid.removeprefix("component:")
            declared[name] = {v.removeprefix("component:")
                              for v, _p in cg.out_edges(cid, "depends_on")}

        observed_deps: dict[str, set[str]] = {name: set() for name in declared}
        for rel, facts in observed.items():
            src_comp = cg.component_of_file(rel)
            if not src_comp:
                continue
            for imp in facts.imports:
                for module, dst_comp in comp_of_module.items():
                    if dst_comp != src_comp and (
                            imp == module or imp.startswith(module + ".")
                            or module.endswith("." + imp)):
                        observed_deps.setdefault(src_comp, set()).add(dst_comp)

        for comp, obs in observed_deps.items():
            dec = declared.get(comp, set())
            for undeclared in sorted(obs - dec):
                findings.append(EvolutionFinding(
                    kind="drift", severity="warning", subject=comp,
                    message=f"component '{comp}' imports '{undeclared}' but the "
                            f"model declares no depends_on edge"))
            for unused in sorted(dec - obs):
                findings.append(EvolutionFinding(
                    kind="drift", severity="note", subject=comp,
                    message=f"declared dependency '{comp}' → '{unused}' is not "
                            f"exercised by any import"))
        return findings
