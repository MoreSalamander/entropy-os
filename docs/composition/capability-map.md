# Phase 1 — Capability Map (discovered, not invented)

Inventory of the four autonomous engines as they exist on disk, taken before a
single line of integration code was written. Every row below was read out of
the engines' actual `engine.py` front doors, `graphs/datahub_bridge.py`
emitters, and venvs — none of it is aspirational.

## The four engines

| | Research | Software | University | Web |
|---|---|---|---|---|
| **Repo** | `~/MoreSalamander/research-engine` | `~/MoreSalamander/code-engine` | `~/MoreSalamander/learn-engine` | `~/MoreSalamander/design-engine` |
| **Package** | `research_engine` | `code_engine` | `learn_engine` | `design_engine` |
| **Entry point** | `Engine.research(topic, progress)` → `(ResearchReport, ContextGraph)` | `CodeEngine.build(request, out_dir)` → `GeneratedProject` | `LearnEngine.start(goal)` / `.next()` / `.submit(activity, answers)` / `.finish()` — **stateful session** | `DesignEngine.generate(request, build_gate)` → `GeneratedSite` |
| **Inputs** | research topic (str) | product idea (str) | learning goal (str); answers (dict) | site brief (str) |
| **Outputs** | report (md + model), Context Graph, KG promotion | verified FastAPI project + `.code_engine/graph.json` sidecar | prereq-DAG roadmap, lesson bundles (`.md`/`.html`), graded mastery evidence | Next.js site + review scores + optional build gate |
| **Agents** | Planner + 6 reasoning agents (Verification first, then Contradiction / Analyst / Discovery / Trend concurrent, Question last) | IntentAnalyzer, research agents (incl. parallel.ai), Architect, ProjectGenerator, 3 static lint agents, Verifier | GoalAnalyzer, EducationalResearch, adaptive policy, PracticeAgent, LessonBuilder, AssessmentAgent | IntentAnalyzer, 6 research workers, DesignSynthesizer, Copywriter, review agents, AutoImprover |
| **External perception** | source fleet (Brave / Serper keys via env → `config.py`) | **parallel.ai keyed adapter** (`PARALLEL_API_KEY`) | EducationalResearch web agents | Brave + Serper site analysis |
| **DataHub platform** | `research-engine` | `code-engine` | `learn-engine` | `design-engine` |
| **DataHub datasets** | `session.<id>` ← `source.<name>` lineage; verification ledger in customProperties | `project.<id>`, `agent.<name>`, `pattern.<name>` | `session.<id>` + agent lineage | `project.<id>`, `site.<host>` |
| **Bridge style** | plain-httpx GMS restli, `probe()` auto-enable, failure degrades to status string | same | same | same |
| **Runtime** | own `.venv` (Python 3.14, pydantic 2.13.4, fastapi 0.141.1 preinstalled) | same | same | same |
| **Progress surface** | typed `ProgressEvent` phases (PLANNING → DONE) | `log()` phase lines `[intent]…[memory]` | `log()` phase lines `[goal]…[memory]` | `log()` phase lines `[intent]…[memory]` |

## Shared substrate (discovered)

All three younger engines import `research_engine` as a library (LLM client,
graph stores, vector index, config). This is a *code* substrate, not a
*runtime* coupling — each engine keeps its own venv, storage, KG, and DataHub
platform.

## Infrastructure state at inventory time

- **DataHub**: real quickstart instance live — GMS `:8080` (health 200),
  frontend `:9002`. Four engine platforms already emitting independently.
- **Ollama**: up, with `gemma4:12b`, `qwen3.5-64k`, `qwen3.5:9b`,
  `llama3.1:8b`, `nomic-embed-text`, more.
- **Temporal**: absent — net-new infrastructure introduced by this repo
  (CLI via Homebrew + `temporalio` SDK in this repo's venv only; engines
  never import Temporal).
- **Prior art**: `entropy-datahub-demo` (frozen judge-facing export of the
  Veritas emitters) proves the local GMS + emission pattern end-to-end.

## What this map dictates about the architecture

1. Engines are **importable async Python** with clean front doors → adapters
   can wrap them in-process, inside each engine's own venv, zero rewrites.
2. Engines already emit **their own** provenance to **their own** DataHub
   platform → federation's job is *only* the cross-platform edges
   (identity, relationships, objective lineage), never re-emission.
3. University is **session-stateful** → the contract needs execution-scoped
   state, and per-engine adapter processes must be long-lived (not
   subprocess-per-call).
4. All four venvs already carry fastapi/pydantic at identical versions →
   the contract surface can be served from inside each engine's venv with
   no dependency work.
5. Every engine tolerates DataHub being down (probe + degrade) → the
   composed system inherits graceful degradation for free and must preserve
   it.
