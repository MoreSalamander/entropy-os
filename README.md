# one-engine

**Four autonomous AI engines converge into one engine — and that engine can be
composed again.**

This is not four applications wired together. It is a *composable intelligence
architecture*: independent domain engines join into a unified system through a
single contract, and the unified system exposes that same contract, so it can
itself become a capability inside something larger. The composition is
recursive by construction, not by special case.

```
        research + software + university + web
                          ↓
                 UNIFIED INTELLIGENCE          ← speaks the contract
                          ↓
                     CAPABILITY                ← consumed by URL, opaquely
                          ↓
                    HIGHER SYSTEM              ← speaks the same contract
                          ↓
                       BEYOND
```

## The four engines stay four engines

| Engine | Repository | Keeps |
| --- | --- | --- |
| Research | [`research-engine`](https://github.com/MoreSalamander/research-engine) | its agents, sources, Context + Knowledge Graphs, `research-engine` DataHub platform |
| Software | [`code-engine`](https://github.com/MoreSalamander/code-engine) | its parallel.ai research, architecture gates, verifier, `code-engine` platform |
| University | [`learn-engine`](https://github.com/MoreSalamander/learn-engine) | its prereq DAG, adaptive policy, mastery evidence, `learn-engine` platform |
| Web | [`design-engine`](https://github.com/MoreSalamander/design-engine) | its site research, design KG, review agents, `design-engine` platform |

**Nothing in those four repositories was modified.** Not one line, not one
dependency. Each adapter runs *inside that engine's own venv* via `PYTHONPATH`
and calls the engine's existing front door. The boundaries are implementation
boundaries; to the user they are capabilities of one product.

## The Universal Engine Contract

The keystone. Every engine — leaf or composite — exposes the same surface:

```
GET  /identity       who are you (with the full composition tree, recursively)
GET  /capabilities   what can you do
GET  /context        what situation are you operating in
GET  /knowledge      what do you know (pointers to graphs, not dumps)
GET  /state          what are you doing
GET  /health         are you well
GET  /events         what happened
POST /execute        do this
POST /events         a fact from outside (never an instruction)
```

Because a composite serves exactly what it consumes, `RemoteEngine` — one
class, ~90 lines — is the entire composition mechanism at *every* level. If
recursion needed a different mechanism one level up, the claim would be false.
It doesn't:

```python
# the unified system holds four of these
CompositeEngine(members={"research": RemoteEngine("http://localhost:9101"), ...})

# a second-level system holds ONE of these, and cannot tell the difference
CompositeEngine(members={"unified": RemoteEngine("http://localhost:9100")})
```

## The four layers, and what each one owns

```
PARALLEL      perception   — the engines' own external acquisition, reused, never duplicated
DATAHUB       memory       — what the system KNOWS: identity, relationships, provenance
AGENTS        reasoning    — each engine's own specialists, untouched
TEMPORAL      execution    — what the system is DOING over time: state, retries, signals, recovery
```

Temporal is never the knowledge graph. DataHub is never the workflow state.
That separation is enforced by packaging: `temporalio` is an optional extra
that only the unified system's venv installs — an engine *cannot* import it.

### DataHub federation, not flattening

Each engine keeps publishing to its own platform. The federation adds one more
platform (`one-engine`) that owns only the cross-domain claims:

```
objective.<id>       the composed run        ← lineage from every stage
stage.<id>.<n>-<e>   one member execution    ← lineage from that engine's OWN datasets
concept.<slug>       cross-domain identity   ← how each domain names the same subject
```

Because stage datasets take their upstreams from datasets the engines emitted
themselves, DataHub's lineage view renders one composed run as a single graph
spanning five platforms. Federation you can see, rather than assert.

### Events describe; they never command

`ResearchCompleted`, `CurriculumCreated`, `SoftwareBuilt`, `SiteGenerated` —
past-tense facts about state changes. No event tells another engine what to
do. Ingesting a fact provably executes nothing
(`tests/test_contract.py::test_ingest_event_records_without_dispatching`).
That restraint is what keeps the engines autonomous while the system behaves
as one.

## Running it

Prerequisites: the four engine repos as siblings with their venvs, Ollama, a
DataHub quickstart on `:8080` (optional), and the Temporal CLI (optional).

```bash
./scripts/up.sh
```

Starts the four adapter servers (ports 9101–9104), the Temporal dev server and
worker, and the unified system on **http://localhost:9100**. `./scripts/up.sh
down` stops it; `status` reports it.

Then ask the system for something that crosses every engine:

```bash
curl -X POST http://localhost:9100/objectives -H 'content-type: application/json' \
  -d '{"inputs":{"topic":"WebGPU compute shaders"}}'
```

Research runs, its discoveries shape the curriculum, the curriculum's learning
order shapes the software request, the software's product name shapes the web
brief — then everything lands in DataHub as one connected graph.

### External perception, and what it costs

The engines' own Parallel and search integrations are preserved and reused —
the unified system never duplicates them. What they actually reach depends on
which keys are set in the environment when `./scripts/up.sh` starts them:

| Key | Used by | Without it |
| --- | --- | --- |
| `PARALLEL_API_KEY` | code-engine | its parallel.ai adapter sits out |
| `BRAVE_SEARCH_API_KEY`, `SERPER_API_KEY` | research-engine, design-engine | keyed web search sits out |

Keyless sources still carry a real run: a live objective on "WebGPU compute
shaders" pulled 219 documents from crossref, arxiv, openalex, github,
stackexchange, hackernews, and gdelt, extracted 109 of them, and rejected 181
items at the evidence gate. Set the keys for broader perception; the
architecture does not change either way.

### Evolution

The system is not limited to one-time generation. `compose.evolve` researches
what changed about a subject, works out from its **own history** what it has
already built for that subject, and updates only what is actually affected:

```bash
curl -X POST http://localhost:9100/objectives -H 'content-type: application/json' \
  -d '{"capability":"compose.evolve","inputs":{"topic":"WebGPU compute shaders"}}'
```

A subject the system has never seen costs one research stage — the other three
skip themselves and record why. A subject with an existing curriculum,
platform, and site updates all three, with the previous product name and
curriculum carried into the new requests. Details in
[docs/evolution.md](docs/evolution.md).

### The second level

```bash
python -m systems.meta_studio      # http://localhost:9200
```

`meta-studio` composes **one** member: the unified system, by URL. Its
pipeline's first stage delegates an entire four-engine composition as a single
capability call, then adds a stage of its own on top. Nothing in
[`systems/meta_studio.py`](systems/meta_studio.py) knows that four engines
exist.

## Degradation is honest

Every dependency can be absent, and the system says so rather than pretending:

- **DataHub down** → objectives still run; provenance URNs are still computed
  and returned; health reports `degraded` with the reason.
- **Temporal down** → the composite runs the *same* pipeline inline through
  the same runtime; provenance records `orchestrator: inline`; health reports
  `degraded` because durability, retries, and human gates are genuinely gone.
- **A member unreachable** → the pipeline stops at that stage rather than
  building confident work on top of nothing. Every member unreachable reads as
  `down`, not `degraded` — a composite with nothing to compose is absent, not
  unwell.

Health is `ok` only when the system can actually deliver what the architecture
promises.

## Tests

```bash
.venv/bin/python -m pytest -q
```

35 tests. The Temporal ones run against a **real** cluster (they skip when
it's not up) with fake members, so a failure there is unambiguously an
orchestration failure rather than a model failure. The recursion tests build a
three-level stack — `holding-co → meta-studio → one-engine → four leaves` —
and assert provenance resolves cleanly through every level.

There is also `scripts/walkthrough.py`, which prints the architecture's claims
by querying the **running** system rather than narrating a diagram.

---

*A [MoreSalamander StudioLabs](https://moresalamander.github.io) Production.*
