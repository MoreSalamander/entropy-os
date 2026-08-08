# A verified run

One objective, four autonomous engines, real artifacts, real provenance.
Everything below was read back out of the running system and a live DataHub
instance — no numbers are estimated.

**Objective** `obj-376d5fa97b43` — *"WebGPU compute shaders"*, audience
"adult beginners who learn by building". Orchestrator: Temporal.
Duration: 08:02:30 → 08:45:01 UTC (~42 minutes).

## What each stage actually did

| # | Engine | Produced |
| --- | --- | --- |
| 1 | research-engine | session `session_86d80f666e84` — 221 entities, 389 claims, 128 relationships, 16 report sections |
| 2 | learn-engine | session `study_7ac7ef4aa4` — subject "Computer Graphics", 8 concepts in prerequisite order |
| 3 | code-engine | project `proj_d44d8dbbf2` — **GPUcademy**, 30 files, 6 components, 14 endpoints |
| 4 | design-engine | project `project_7a66629ae4cb` — 34 files, 5 pages, all five review agents at 100 |

Research acquisition, in its own numbers: 112 tasks spawned, 219 documents
fetched, 110 deduped or already known, 109 extracted, **181 items rejected at
the evidence gate**, 54 entities and 48 relationships promoted to the
Knowledge Graph. Sources: crossref (29), arxiv (25), openalex (24), github
(11), stackexchange (9), hackernews (8), gdelt (3) — all keyless, since no
search API keys were configured for this run.

## The claim that matters: information crossed domains

Not "four engines ran." Each stage's request was built from what the previous
ones produced, and it survived all the way into rendered output:

- learn-engine derived 8 concepts → code-engine's build request named them in
  order → it produced a platform called **GPUcademy** with a
  `/users/{id}/progress` endpoint, which is the per-concept mastery tracking
  the curriculum-informed request asked for.
- code-engine's product name → design-engine's site brief → the generated copy
  in `lib/content.ts` (434 lines, 53 domain-term mentions) reads:

  > "Master WebGPU compute shaders through hands-on projects and a
  > comprehensive curriculum covering the API, debugging tools, and GPU
  > architecture."

  Those three named topics are curriculum concepts 1, 3, and 4 from stage 2.
  The web engine never saw stage 2 — it saw a brief the pipeline built from it.

## Honest verdicts, not flattering ones

code-engine returned `verification_passed: False` with a concrete reason:
`[pytest] tests/test_quiz_service.py: AttributeError… (repair declined)`.

The pipeline recorded that as a **completed stage with a failing verdict**, not
as a stage failure — the engine did its job and reported truthfully. The verdict
travels three ways: as a `SoftwareVerificationFailed` semantic event, as an
output field, and as a queryable DataHub property
(`out_verification_passed: False`). Nothing downstream was blocked, and nothing
was hidden.

## Federation: one run, five platforms, one graph

Each stage's lineage upstreams are the engine's **own** dataset plus the
previous stage, so the composed run renders in DataHub as a single connected
graph spanning five platforms:

```
research-engine,session.session_86d80f666e84
        ↑
one-engine,stage.obj-376d5fa97b43.1-research-engine
        ↑                    learn-engine,session.study_7ac7ef4aa4
one-engine,stage.obj-376d5fa97b43.2-learn-engine  ←────┘
        ↑                    code-engine,project.proj_d44d8dbbf2
one-engine,stage.obj-376d5fa97b43.3-code-engine   ←────┘
        ↑                    design-engine,project.project_7a66629ae4cb
one-engine,stage.obj-376d5fa97b43.4-design-engine ←────┘
        ↑
one-engine,objective.obj-376d5fa97b43   (5 upstreams: 4 stages + the concept)
```

And cross-domain identity, with receipts —
`one-engine,concept.webgpu-compute-shaders`:

```
subject             : WebGPU compute shaders
research_session    : session_86d80f666e84
curriculum_session  : study_7ac7ef4aa4
curriculum_concepts : WebGPU Compute Shader API, Compute Shaders Fundamentals,
                      Debugging and Profiling Compute Shaders, GPU Architecture, …
software_project    : proj_d44d8dbbf2
software_product    : GPUcademy
web_project         : project_7a66629ae4cb
```

Four domains, four independent identifier schemes, one concept — and every
entry is a real identifier that domain actually issued.

## Evolution, against this run's own history

A later objective, `obj-0bfdf845b130` — `compose.evolve` on the same subject —
emitted `ImpactAnalyzed` **before any stage ran**:

```json
{"concept_slug": "webgpu-compute-shaders",
 "prior_objectives": ["obj-24a41bfd1568", "obj-376d5fa97b43"],
 "affected": ["research", "software", "university", "web"],
 "unaffected": [], "is_new_subject": false}
```

The system read its own record, found what it had built, and decided what
needed updating before spending anything. Then it behaved like an update
rather than a rebuild, in three observable ways:

**It asked a different question.** Research ran on *"What has recently changed
about WebGPU compute shaders: new releases, deprecations, and current best
practice"* — 169 entities, 192 claims — not a re-run of the original topic.

**It carried the prior curriculum forward.** The new goal was built from the
impact report: *"Understand WebGPU compute shaders as it stands today,
including what recently changed and why. The previous curriculum covered:
WebGPU Compute Shader API, Compute Shaders Fundamentals, Debugging…"*

**The curriculum grew where the change was.** 8 concepts became 10, and the
two additions are exactly the ones an update should produce:

```
+ Recent Changes in WebGPU Compute Shaders
+ Why Recent Changes Matter
```

That is the difference between regenerating and evolving: the system did not
rediscover the subject, it discovered what had moved and folded that into what
it already taught.

## Two problems this run exposed

**Temporal caught a bug by refusing to lose the run.** Activities addressed by
name carry no inferable return type, so the workflow received bare dicts:
`'dict' object has no attribute 'result'`. It surfaced as a workflow task
failing and retrying *forever* rather than the run dying — Temporal declining to
discard a run over a code defect. Fixed with `result_type=`.

**Health was answering the wrong question.** An adapter reported `ok` while its
engine could not even be imported, and the problem only surfaced once a stage
had already run and failed. Health now checks whether the engine module is
importable, and the composite reports `degraded` when DataHub or Temporal is
absent — because provenance and durability are promises, not extras.

A third, smaller one: research-engine's reasoning agents exceeded its own 120s
LLM default under a composed Context Graph (Ollama returning 500 after exactly
2m0s). Raised through the engine's public Config object, so its repository
stays untouched.
