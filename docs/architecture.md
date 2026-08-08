# Architecture

How four autonomous engines become one engine, and why the result can be
composed again.

## The invariants

1. **Each engine stays autonomous.** Own codebase, agents, domain logic,
   Parallel integration, DataHub integration, Context Graph, Knowledge Graph,
   workflows, deployment. Verified literally: the four repositories are
   unmodified, and nothing is installed into their venvs — adapters reach the
   interpreter through `PYTHONPATH`.
2. **They become one product.** One surface, one objective, one narration.
3. **DataHub is the semantic connective tissue.** Domain graphs stay
   domain-aware; the federation adds cross-domain edges over them.
4. **Temporal is durable orchestration, never state storage.** Enforced by
   packaging: `temporalio` is an optional extra of *this* repo only.
5. **The unified system is itself an engine.** It serves the contract it
   consumes.

## The Universal Engine Contract

Nine routes, one shape, every level:

| Route | Answers |
| --- | --- |
| `GET /identity` | who are you — including the recursive composition tree |
| `GET /capabilities` | what can you do |
| `GET /context` | what situation are you in |
| `GET /knowledge` | what do you know (pointers to graphs, not dumps) |
| `GET /state` | what are you doing |
| `GET /health` | are you well |
| `GET /events` | what happened |
| `POST /execute` | do this |
| `POST /events` | a fact from outside |

Three implementations satisfy it, and callers cannot tell them apart:

- **`LeafAdapter`** — wraps one specialized engine's front door.
- **`RemoteEngine`** — proxies any contract server over HTTP.
- **`CompositeEngine`** — wraps many members, exposing the same contract.

### Two rules that make the contract load-bearing

**Failures are results, not HTTP errors.** `POST /execute` returns
`status: "failed"` with the error and full provenance. A 500 means transport
or implementation fault. A composite must always be able to distinguish "it
ran and failed" from "I could not reach it" — the difference decides whether
to retry.

**Opacity at the boundary, transparency in provenance.** A composite serves
member capabilities as its own (`capability.engine == "one-engine"`). Which
member actually ran is recorded in `Provenance.children`, nested one level per
composition level. Consumers can ignore that tree (opacity) or descend it
(transparency); both are legitimate, and that is exactly the abstraction
recursion needs.

## Composition, level by level

```
holding-co                       CompositeEngine, pipelines={}
   └── meta-studio               CompositeEngine, pipelines={studio.launch_venture}
         └── one-engine          CompositeEngine, pipelines={compose.learning_platform}
               ├── research-engine     LeafAdapter → research_engine.Engine
               ├── code-engine         LeafAdapter → code_engine.CodeEngine
               ├── learn-engine        LeafAdapter → learn_engine.LearnEngine
               └── design-engine       LeafAdapter → design_engine.DesignEngine
```

Every edge in that tree is a `RemoteEngine` holding a URL. One mechanism, all
levels — which is the difference between recursion and a two-level special
case.

### The knife-edge: pipelines are per-composite

A composite runs a capability as a *composition* only if it declares that
pipeline itself:

```python
if req.capability in self.pipelines:   # MY pipeline → run the stages
    return await self._execute_composed(req)
return await self._execute_atomic(req)  # someone else's → delegate whole
```

This is the single most important line in the system. `meta-studio` inherits
`compose.learning_platform` in its manifest, but does not *declare* it — so it
delegates the whole four-engine composition to its member as one capability
call. Had pipelines been a module-level registry, the second level would have
tried to run its member's pipeline with members it does not have, and
recursion would have been false at depth two. Covered by
`tests/test_recursion.py::test_members_composed_capability_is_delegated_not_re_run`.

## Cross-domain intelligence

Information flows because each stage builds its inputs from what earlier
stages produced:

```
research.investigate        topic
        ↓ (discoveries)
university.design_curriculum  goal → learning_order
        ↓ (learning_order)
software.build              "platform teaching <concepts in order>"
        ↓ (product_name)
web.generate_site           "site for <product>"
```

Add a pipeline to a registry and a new cross-domain path exists; nothing else
in the system changes.

## DataHub federation

Three dataset kinds under the `one-engine` platform, and only these:

```
concept.<slug>          cross-domain identity — every domain's local name for one subject
stage.<obj>.<n>-<eng>   one member execution  — upstreams: that engine's OWN datasets
objective.<obj>         the composed run      — upstreams: every stage + the concept
```

The engines' own emissions are never rewritten or re-published. Because stage
datasets take their upstreams from datasets the engines emitted themselves,
one composed run renders in DataHub's lineage view as a single connected graph
spanning five platforms.

Identity resolution carries receipts: a domain appears in a `concept` record
only if it produced a real identifier
(`tests/test_federation.py::test_identity_resolution_only_claims_what_actually_happened`).

## Temporal

`ComposedObjectiveWorkflow` owns sequencing, retries, timeouts, human approval
signals, and durable history. Activities own every effect. The workflow module
imports only pure pipeline shape, so the sandbox stays deterministic.

Both orchestration paths — Temporal activities and the inline fallback — call
the *same* functions in `orchestration/runtime.py`. One narration, one
federation, one provenance shape, whichever driver is in charge. Temporal adds
durability; it never changes what a stage *is*.

Two implementation details worth knowing, both found by running it:

- Activities and workflows addressed **by name** carry no inferable return
  type. Without `result_type=`, the SDK hands back bare dicts. This surfaced
  as `'dict' object has no attribute 'result'` — and as an *infinitely
  retrying workflow task*, which is Temporal correctly refusing to lose a run
  over a code bug.
- `workflow_id == objective_id`, so re-submitting an objective attaches to the
  running workflow instead of starting a second one.

## Honest degradation

| Missing | Behavior | Health |
| --- | --- | --- |
| DataHub | objectives run; URNs still computed and returned | `degraded` |
| Temporal | same pipeline, inline; provenance says `orchestrator: inline` | `degraded` |
| One member | pipeline stops at that stage | `degraded` |
| All members | nothing to compose | `down` |
| Engine module unimportable | adapter is up but cannot work | `down` |

The last row was added after a real failure: the adapter reported `ok` while
its engine could not be imported, and the problem only surfaced when a stage
ran. Health has to answer "can I do the work", not "is my server running".
