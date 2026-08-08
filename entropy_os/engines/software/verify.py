"""Phase 9 — Continuous Verification. Never assume generated software works.

Real tools, real subprocesses, structured results:

    ruff (static analysis) → pytest (the generated project's own tests)
    → Security Agent lint → Performance Agent lint → Code Review lint

Every failure maps through the Context Graph: file → component → feature →
requirement, and lands as a `problem` node. The repair loop is bounded and
gated: the LLM proposes a corrected file, deterministic gates require the
target to exist inside the project, parse as Python, and not delete tests;
then the whole verification re-runs. Residual failures are recorded as
known_problems — the report never launders a red suite into a green one.

Runner detail: generated projects execute with the ENGINE's interpreter
(fastapi/sqlalchemy/pytest present) and PYTHONPATH pointed at the project —
standalone installs still work via the generated requirements files.
"""

from __future__ import annotations

import ast
import asyncio
import json
import re
import sys
from pathlib import Path

from entropy_os.engines.research.llm.client import LLMClient, LLMUnavailable

from .graphs.context_graph import SoftwareContextGraph
from .models import CheckResult, CheckStatus, VerificationReport

_REPAIR_SCHEMA = {
    "type": "object",
    "properties": {"file": {"type": "string"},
                   "content": {"type": "string"},
                   "explanation": {"type": "string"}},
    "required": ["file", "content", "explanation"],
}

_REPAIR_SYSTEM = """You repair one file of a generated FastAPI project so its tests pass.
You receive the failing test output and the current content of the most
implicated file. Return the COMPLETE corrected file content (not a diff).
Change only what the failure requires. Never remove or weaken tests."""


async def _run(cmd: list[str], cwd: Path, env_path: Path,
               timeout_s: int = 240) -> tuple[int, str]:
    import os
    env = dict(os.environ)
    env["PYTHONPATH"] = str(env_path)
    proc = await asyncio.create_subprocess_exec(
        *cmd, cwd=cwd, env=env,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
    except (TimeoutError, asyncio.TimeoutError):
        proc.kill()
        return 1, f"timed out after {timeout_s}s"
    return proc.returncode or 0, out.decode(errors="replace")


class Verifier:
    def __init__(self, llm: LLMClient, max_repair_rounds: int = 2):
        self.llm = llm
        self.max_repair_rounds = max_repair_rounds

    # ------------------------------------------------------------------ #
    async def ruff_check(self, root: Path) -> CheckResult:
        code, out = await _run([sys.executable, "-m", "ruff", "check",
                                "--output-format", "json", "app", "tests"],
                               root, root)
        try:
            rows = json.loads(out) if out.strip().startswith("[") else []
        except json.JSONDecodeError:
            rows = []
        failures = [{"file": r.get("filename", "").split(str(root) + "/")[-1],
                     "message": f"{r.get('code')}: {r.get('message')}"}
                    for r in rows]
        return CheckResult(check="ruff",
                           status=CheckStatus.PASS if code == 0 else CheckStatus.FAIL,
                           detail=f"{len(failures)} findings",
                           failures=failures[:20])

    async def pytest_check(self, root: Path) -> CheckResult:
        code, out = await _run([sys.executable, "-m", "pytest", "-q",
                                "--no-header", "tests"], root, root)
        failures: list[dict] = []
        for m in re.finditer(r"FAILED (tests/[\w/]+\.py)::(\w+)(?: - (.*))?", out):
            failures.append({"file": m.group(1), "test": m.group(2),
                             "message": (m.group(3) or "")[:200]})
        if code != 0 and not failures:  # collection errors etc.
            failures.append({"file": "tests", "test": "collection",
                             "message": out[-400:]})
        return CheckResult(check="pytest",
                           status=CheckStatus.PASS if code == 0 else CheckStatus.FAIL,
                           detail=out.strip().splitlines()[-1][:200] if out.strip() else "",
                           failures=failures)

    # ------------------------------------------------------------------ #
    def _map_failures(self, results: list[CheckResult],
                      cg: SoftwareContextGraph) -> None:
        """file → component enrichment, then problems land in the graph."""
        for res in results:
            for failure in res.failures:
                comp = cg.component_of_file(failure.get("file", ""))
                if comp:
                    failure["component"] = comp
        cg.record_verification([r for r in results
                                if r.status == CheckStatus.FAIL])

    def _implicated_file(self, failure: dict, root: Path,
                         cg: SoftwareContextGraph) -> str | None:
        """Root-cause candidate: the failing test's component's most relevant
        source file (router first, then service), else the failing file."""
        comp = failure.get("component") or cg.component_of_file(
            failure.get("file", ""))
        if comp:
            for candidate in (f"app/routers/{comp}.py", f"app/services/{comp}.py",
                              "app/models.py", "app/schemas.py"):
                if (root / candidate).exists():
                    return candidate
        f = failure.get("file", "")
        return f if (root / f).exists() else None

    async def _attempt_repair(self, root: Path, failure: dict, test_output: str,
                              cg: SoftwareContextGraph) -> bool:
        target = self._implicated_file(failure, root, cg)
        if target is None:
            return False
        current = (root / target).read_text()
        try:
            proposal = await self.llm.chat_json(
                "extract", _REPAIR_SYSTEM,
                f"FAILURE:\n{failure}\n\nTEST OUTPUT (tail):\n{test_output[-1500:]}"
                f"\n\nFILE {target}:\n{current[:6000]}",
                _REPAIR_SCHEMA)
        except LLMUnavailable:
            return False
        file_rel = str(proposal.get("file") or target)
        content = str(proposal.get("content") or "")
        # ---- deterministic gates on the proposed patch ----------------
        dest = (root / file_rel).resolve()
        if not str(dest).startswith(str(root.resolve())):
            return False                      # path escape → rejected
        if file_rel.startswith("tests/"):
            return False                      # repairs never touch tests
        if not content.strip():
            return False
        try:
            ast.parse(content)
        except SyntaxError:
            return False                      # unparseable patch → rejected
        if not dest.exists():
            return False                      # repairs edit, never invent files
        dest.write_text(content)
        return True

    # ------------------------------------------------------------------ #
    async def verify(self, root: Path, cg: SoftwareContextGraph,
                     extra_checks: list[CheckResult] | None = None,
                     log=print) -> VerificationReport:
        report = VerificationReport()
        rounds = 0
        while True:
            ruff = await self.ruff_check(root)
            tests = await self.pytest_check(root)
            results = [ruff, tests] + list(extra_checks or [])
            failing = [r for r in results if r.status == CheckStatus.FAIL]
            if not failing or rounds >= self.max_repair_rounds:
                self._map_failures(results, cg)
                report.results = results
                report.repair_rounds = rounds
                for r in failing:
                    for f in r.failures[:6]:
                        report.known_problems.append(
                            f"[{r.check}] {f.get('file', '?')}: "
                            f"{f.get('message', '')[:120]}")
                return report
            # repair round: take the first structured pytest failure first,
            # else the first ruff finding
            self._map_failures(results, cg)
            primary = (tests.failures[0] if tests.status == CheckStatus.FAIL
                       and tests.failures else
                       ruff.failures[0] if ruff.failures else None)
            if primary is None:
                report.results = results
                report.repair_rounds = rounds
                return report
            rounds += 1
            log(f"[verify] round {rounds}: repairing after "
                f"{primary.get('file')}::{primary.get('test', primary.get('message', ''))[:60]}")
            repaired = await self._attempt_repair(root, primary, tests.detail, cg)
            if not repaired:
                report.results = results
                report.repair_rounds = rounds
                for r in failing:
                    for f in r.failures[:6]:
                        report.known_problems.append(
                            f"[{r.check}] {f.get('file', '?')}: "
                            f"{f.get('message', '')[:120]} (repair declined)")
                return report
