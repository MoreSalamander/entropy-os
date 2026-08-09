# research-engine

**General Research Intelligence Engine** — a MoreSalamander StudioLabs production.

Enter any research topic. The engine plans the investigation, fans out a fleet
of specialized research agents across live sources in parallel, extracts
structured evidence, builds a session **Context Graph**, promotes verified
knowledge into a persistent **Knowledge Graph**, reasons over both with six
graph agents, and produces a full research report — every claim source-linked,
every confidence score deterministic.

```
User Question → Research Planning → Parallel Information Acquisition
→ Evidence Extraction → Context Graph Construction → Knowledge Graph
Integration → Multi-Agent Reasoning → Research Report + Discoveries
```

Design law (the deterministic-scaffold thesis): **LLMs propose, deterministic
code decides.** Every LLM output passes a validation gate before storage;
provenance is built from fetched documents, never model text; a claim without
evidence does not exist.

## Quick start

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
# requires Ollama running locally (models configurable in config.yaml)
.venv/bin/python -m research_engine "the future of AI hardware"
```

API server:

```bash
.venv/bin/uvicorn research_engine.api.app:app --port 8017
```

| Endpoint | Purpose |
|---|---|
| `POST /research {"topic": …}` | start a session (background) |
| `GET /research/{id}` | phase, counters, report JSON |
| `GET /research/{id}/report.md` | rendered markdown report |
| `GET /research/{id}/events` | SSE progress stream |
| `GET /graph/context/{id}` | session Context Graph snapshot |
| `GET /graph/knowledge/stats` · `/entity/{name}` · `/paths?a=&b=` | Knowledge Graph queries |
| `GET /sources/status` | the source honesty table |

## The three foundational systems

### 1. Parallel Research Engine
The planner staffs the spec's ten-agent roster (Academic, Industry, Patent,
Open Source, Market, News, Expert Opinion, Historical Context, Technical
Documentation, Regulatory), maps each onto live source adapters, and the
orchestrator fans out `agent × source × query-variant` tasks through an
asyncio worker pool — global concurrency is a config knob (default 32,
scales to hundreds; free-API rate limits, not the architecture, are the
ceiling). Per-source semaphores + politeness intervals keep every API happy.

### 2. Context Graph
Per-session situational awareness, updated live as each document lands:
active entities (within-session resolution), claims + evidence, research
branches, deterministic contradiction candidates, confidence rollups, open
questions. Snapshot persisted per session. **If a local DataHub is running**
(`datahub.enabled: auto` probes GMS), each session is emitted as a dataset
with per-source lineage upstreams and the verification ledger as properties —
research provenance as first-class metadata.

### 3. Knowledge Graph
Persistent across all sessions. Cross-session entity resolution runs three
rungs — exact/alias match → embedding similarity (Qdrant) → judge-model
confirmation (a *different model family* than the extractor; no judge, no
merge). Edges accumulate history: first_seen/last_seen, session list,
evidence counts. `paths_between` powers cross-domain reasoning; the planner
queries the KG before every run so known entities become context, not
re-research.

## Graph reasoning agents

| Agent | Mechanism |
|---|---|
| Verification | pure deterministic gate: reliability ≥ 0.7 single-source, or ≥ 2 independent sources ≥ 0.45 |
| Contradiction | deterministic opposite-polarity pairing → judge confirms; never auto-confirms |
| Research Analyst | per-branch summaries voiced only from verified claim statements |
| Discovery | cross-domain = graph paths whose endpoints are evidenced by different source categories |
| Trend | emerging = measured: recent 90-day evidence ≥ 2× trailing-year baseline |
| Question | unresolved plan questions + weak entities → concrete follow-up paths |

## Sources

**Live keyless (14):** arXiv, OpenAlex, Semantic Scholar, PubMed, Crossref
(incl. ACM/IEEE metadata), Wikipedia, GitHub, GitLab, Hugging Face,
Hacker News, Stack Exchange, GDELT news, data.gov, Reddit (degraded —
public JSON, honestly flaky).

**Keyed, fully implemented, disabled fail-closed until a key is pasted into
`config.yaml`:** Brave Search, Serper, NewsAPI, IEEE Xplore, PatentsView
(USPTO), Kaggle. **WIPO** is an honest stub — no free API exists, and the
status table says so.

Every run's report includes the full source status table: live / degraded /
needs_key / error, with call and document counts.

## Storage backends (config flips, not refactors)

| Layer | Embedded default | Spec server (flip in config.yaml) |
|---|---|---|
| Graph | NetworkX + atomic JSON (+.bak) | Neo4j (`graph.backend: neo4j`, `pip install neo4j`) |
| Vectors | Qdrant **embedded local mode** | Qdrant server (`vectors.url`) |
| Relational | SQLite | PostgreSQL (`db.url`, `pip install psycopg[binary]`) |
| Queue | asyncio worker pool | Redis (`queue.backend: redis`, `pip install redis`) |
| LLM | Ollama (role-routed, judge-separated) | any OpenAI-compatible endpoint via `llm.base_url` |

## Report

Sixteen fixed sections, always all present, each carrying an `item_count` of
real rendered content (content fidelity is countable): Executive Summary ·
What Changed Recently? · What Is the Consensus? · What Remains Uncertain? ·
What Connections Were Discovered? · Research Map · Major Entities ·
Key Findings · Evidence Table · Timeline · Arguments For/Against · Unknowns ·
Future Predictions (labeled extrapolation, never fact) · Related Discoveries ·
Confidence Scores · Source References. Empty sections say so instead of padding.

## Tests

```bash
.venv/bin/python -m pytest   # 42 offline deterministic tests, no network, no Ollama
```

## Continuous learning

Every finished session: verified claims promote into the KG; every extracted
document's hash lands in the ledger so no later session re-extracts it; the
next plan for a related topic starts from what the KG already knows and the
Question agent's follow-up paths.
