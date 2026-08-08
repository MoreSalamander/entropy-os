# code-engine

**AI-native Software Intelligence and Generation Platform** — third engine of
the MoreSalamander family, built on the
[research-engine](https://github.com/MoreSalamander/research-engine) substrate.

Enter a software idea. The platform extracts a structured specification,
researches the problem in parallel, designs a gated architecture, generates a
complete runnable FastAPI project whose semantic model is built **by
construction**, verifies it with real tools, and learns from the outcome —
across projects.

```
User Idea → Product Intelligence → Parallel Software Research
→ Software Context Graph → Software Knowledge Graph
→ Architecture Intelligence → AI Engineering Team → Generated Software
→ Continuous Verification → Impact Analysis → Evolution → Reusable Knowledge
```

The generated repository carries its own self-model in
`.code_engine/graph.json`: every file knows which component, feature, and
requirement it exists for. Impact analysis and evolution checks read that
sidecar — the software the AI generated is software the AI can still reason
about later.

## Quick start

```bash
python3 -m venv .venv
.venv/bin/pip install -e ../research-engine -e . ruff
# requires Ollama running locally
.venv/bin/python -m code_engine build "Build an AI research platform"
.venv/bin/python -m code_engine impact <project_dir> <component>
.venv/bin/python -m code_engine evolve <project_dir>
.venv/bin/python -m code_engine patterns
```

API: `.venv/bin/uvicorn code_engine.api.app:app --port 8019`.

## The engineering organization (16 named roles, every mechanism real)

| Role | Mechanism |
|---|---|
| Product Agent | schema-gated spec + MoSCoW floor + injected test/validation baselines |
| Architect Agent | gated design: requirement coverage enforced, entity single-ownership, CRUD completion, ADRs into the graph |
| 6 Research Agents | parallel: PyPI (live), OSV.dev (live), GitHub, HN, Wikipedia, official docs; Parallel.ai keyed fail-closed |
| Implementation Agents | deterministic generation: routers/services/models/schemas/frontend/Docker |
| Testing Agent | tests generated per feature with provenance, executed for real |
| Security Agent | static rules: no eval/exec/shell/pickle, no secret literals, no string SQL, schemas on mutating routes + OSV live |
| Performance Agent | ast rules: queries-in-loops (N+1), blocking sleeps in request paths |
| Code Review Agent | layer boundaries (routers never import models), function length, route docstrings |
| Documentation Agent | architecture.md / api.md derived from the model, never freehand |

## Verification is execution, not opinion

`ruff` and the generated project's own `pytest` suite run as subprocesses;
the three lint agents join as first-class checks. Failures map through the
graph (file → component → feature → requirement) and land as problem nodes.
The repair loop is bounded (2 rounds) and gated — patches must parse, stay
inside the project, and never touch tests; a red suite is reported red.

## Change impact & evolution

`impact` walks the sidecar graph: transitive dependents, affected APIs,
tests to re-run, requirements at risk, suspect docs, infra touchpoints —
before anyone edits code. `evolve` re-verifies and checks reality against
the model: ast-observed imports vs declared dependencies (drift), OSV
advisories, PyPI staleness, doc drift. On-demand / cron-able, not a daemon.

## Honest constraints

- **One stack, deep:** FastAPI + SQLAlchemy/SQLite + pytest + static JS.
  Other stacks enter the Knowledge Graph as researched patterns before they
  become generation targets. Custom endpoints beyond CRUD generate visible
  `implemented: false` stubs recorded as known problems.
- **Semantic modeling scope:** by-construction for generated projects +
  Python-`ast` drift analysis. Arbitrary polyglot repos are out.
- **Cross-project learning** ranks patterns by our own verification outcomes
  (success rate, repair rounds). No invented telemetry.
- **DataHub** (auto-probed): each project emitted with research + pattern
  lineage and per-check verification status.

## Tests

```bash
.venv/bin/python -m pytest   # 25 offline tests — including running a
                             # generated project's own suite in a subprocess
```
