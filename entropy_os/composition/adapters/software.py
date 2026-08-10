"""Software engine adapter — wraps entropy_os.engines.software.CodeEngine behind the contract.

The engine's pipeline (intent → parallel.ai-backed research → KG priors →
architecture → generation → verification → sidecar → DataHub) runs untouched.
Its log() phase lines become semantic progress events, and its verification
verdict becomes a first-class fact rather than a buried string.
"""

from __future__ import annotations

import os
from pathlib import Path

from ..contract import ArtifactRef, CapabilitySpec, Determinism, ExecuteRequest, FieldSpec
from ..llm import build_llm
from .base import Emit, LeafAdapter, Vouch


class SoftwareAdapter(LeafAdapter):
    name = "code-engine"
    description = ("Software generation: product intent, parallel.ai-backed "
                   "research, architecture with deterministic gates, code "
                   "generation, verification (ruff + pytest + lint agents), "
                   "self-model sidecar, cross-project memory.")
    datahub_platform = "code-engine"
    member_key = "software"
    engine_module = "entropy_os.engines.software.engine"
    events_emitted = ["SoftwareBuildProgress", "SoftwareBuilt",
                      "SoftwareVerificationFailed"]

    def __init__(self):
        super().__init__()
        self._engine = None

    def _get(self):
        if self.llm_changed():
            self._engine = None       # rebuilt below against the new routing
        if self._engine is None:
            from entropy_os.engines.software.engine import CodeEngine
            self._engine = CodeEngine(
                llm=build_llm(),      # None on local → the engine's own client
                parallel_key=os.environ.get("PARALLEL_API_KEY", ""),
                datahub_gms=os.environ.get("DATAHUB_GMS",
                                           "http://localhost:8080"))
        return self._engine

    def capabilities(self) -> list[CapabilitySpec]:
        return [CapabilitySpec(
            name="software.build",
            summary="Turn a product request into a generated, verified "
                    "FastAPI project that ships with its own semantic-model "
                    "sidecar.",
            long_running=True,
            inputs={
                "request": FieldSpec(type="string", required=True,
                                     description="what to build"),
                "out_dir": FieldSpec(type="string",
                                     description="optional output directory"),
            },
            outputs={
                "project_id": FieldSpec(),
                "out_dir": FieldSpec(description="generated project root"),
                "verification_passed": FieldSpec(type="boolean"),
                "stack": FieldSpec(type="object"),
            },
            tags=["software", "generation"])]

    async def _run(self, req: ExecuteRequest, emit: Emit, vouch: Vouch):
        request = str(req.inputs.get("request", "")).strip()
        if not request:
            raise ValueError("software.build requires inputs.request")
        engine = self._get()

        def log(line) -> None:
            # The engine narrates its phases as "[intent] …" lines; forward
            # them verbatim so the unified feed shows the real pipeline.
            emit("SoftwareBuildProgress", subject=request[:80], line=str(line))

        out_dir = req.inputs.get("out_dir")
        project = await engine.build(request,
                                     out_dir=Path(out_dir) if out_dir else None,
                                     log=log)

        urn = self.dataset_urn(f"project.{project.project_id}")
        passed = bool(project.verification and project.verification.passed)

        # Every check this engine ran, reported at the fidelity it was run
        # with. All of them are HARD: ruff and pytest are subprocesses whose
        # exit codes are facts, and the security / performance / review agents
        # — despite the name — are AST and regex analysis, not model calls.
        # The only LLM in the verification loop PROPOSES repairs and decides
        # nothing, which is the whole doctrine in one place.
        for check in (project.verification.results if project.verification else []):
            skipped = check.status.value == "skipped"
            vouch(
                gate=f"software.{check.check}",
                determinism=Determinism.HARD,
                # A skipped check has not passed. Counting it as a pass is how
                # a verification surface starts lying by omission.
                passed=check.status.value == "pass",
                evidence=check.detail or f"{check.check}: {check.status.value}",
                status=check.status.value,
                skipped=skipped,
                failures=check.failures[:10],
                failure_count=len(check.failures),
            )
        if project.verification and project.verification.known_problems:
            # Residue the engine chose to ship with, named rather than buried.
            vouch(gate="software.known_problems", determinism=Determinism.HARD,
                  passed=False,
                  evidence="; ".join(project.verification.known_problems[:5]),
                  count=len(project.verification.known_problems))
        endpoints = sum(len(c.endpoints)
                        for c in project.architecture.components)

        emit("SoftwareBuilt", subject=urn,
             project_id=project.project_id,
             product_name=project.spec.product_name,
             files_written=project.files_written,
             components=len(project.architecture.components),
             endpoints=endpoints, verification_passed=passed)
        if not passed:
            emit("SoftwareVerificationFailed", subject=urn,
                 known_problems=(project.verification.known_problems
                                 if project.verification else ["no report"]))

        outputs = {
            "project_id": project.project_id,
            "product_name": project.spec.product_name,
            "out_dir": str(project.out_dir),
            "files_written": project.files_written,
            "stack": project.architecture.stack,
            "components": len(project.architecture.components),
            "endpoints": endpoints,
            "requirements": len(project.spec.requirements),
            "verification_passed": passed,
            "repair_rounds": (project.verification.repair_rounds
                              if project.verification else 0),
        }
        artifacts = [
            ArtifactRef(kind="project", path=str(project.out_dir),
                        description=f"generated project: "
                                    f"{project.spec.product_name}"),
            ArtifactRef(kind="sidecar",
                        path=str(Path(project.out_dir) / ".code_engine"
                                 / "graph.json"),
                        description="self-model sidecar (context graph)"),
        ]
        return outputs, artifacts, [urn], []

    async def aclose(self) -> None:
        if self._engine is not None:
            await self._engine.aclose()
            self._engine = None
