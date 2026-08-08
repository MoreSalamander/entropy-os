# Evolution

The system does not only generate once. When new information appears about
something it has already built, it works out what that actually affects and
updates only that.

## The loop

```
new information about X
        ↓
research.investigate        what has changed about X?
        ↓
impact analysis             what has this system already made for X?
        ↓
university.design_curriculum   only if a curriculum exists
software.build                 only if software exists
web.generate_site              only if a site exists
```

`compose.evolve` is a normal composed pipeline — same contract, same
provenance, same DataHub federation. Two things make it evolutionary.

## 1. Impact is determined before any work happens

`ImpactAnalyzed` is the first fact in an evolution objective, ahead of even
`ObjectiveStarted`. It answers three questions from the system's own durable
history:

- Which prior objectives had this subject? (matched by concept slug, so
  "WebGPU Compute Shaders" and "webgpu compute shaders" are one subject —
  the same identity rule the federation uses to publish a concept.)
- What did each engine produce inside them?
- Therefore which engines have something to update?

```json
{
  "kind": "ImpactAnalyzed",
  "payload": {
    "concept_slug": "webgpu-compute-shaders",
    "prior_objectives": ["obj-376d5fa97b43"],
    "affected": ["research", "software", "university", "web"],
    "unaffected": [],
    "is_new_subject": false
  }
}
```

### Where the answer comes from — and why it matters for composability

Impact reads the composite's own `StageCompleted` narration, not each
engine's private event vocabulary. Every stage records the handles by which
its work can later be found:

```python
IDENTIFYING_OUTPUTS = ("session_id", "project_id", "product_name",
                       "learning_order", "subject", "out_dir")
```

One declaration, used by both the DataHub federation (as queryable dataset
properties) and impact analysis (as the record of what exists). An engine that
joins the system later becomes legible to both by naming its outputs
conventionally — there is no table in `impact.py` to update, and the new
engine needs no knowledge that impact analysis exists.

The first version of this module *did* read per-engine event kinds
(`CurriculumCreated` → `session_id`, `SoftwareBuilt` → `project_id`). It
worked, and it was wrong: it made every future engine a change to this file.

## 2. Stages skip themselves, and say why

`PlannedStage.skip_if` is a deterministic, data-only predicate evaluated
inside the workflow itself. A skipped stage costs no activity, no engine call,
and no time:

```python
PlannedStage(3, "software", "software.build", _evolve_software_inputs,
             skip_if=lambda i, acc: not _affected(acc, "software"),
             skip_reason="no existing software for this subject")
```

A skip is modeled as a **completed** result carrying `skipped: true` and its
reason — not as a failure. An evolution run that finds no software to rebuild
has not gone wrong; it has correctly done less work. The reason travels in
provenance, so the record shows why a stage was passed over rather than
leaving a hole.

| Situation | What runs |
| --- | --- |
| Subject the system has never seen | research only; three stages skip |
| Subject with a curriculum but no software | research + curriculum |
| Subject with curriculum, platform, and site | all four, informed by what existed |

## What "informed by what existed" means

The update is not a fresh build with the same words. Prior artifacts shape the
new request:

```python
def _evolve_software_inputs(inputs, acc):
    prior = _affected(acc, "software")          # from impact analysis
    product = prior.get("product_name") or f"{topic} Academy"
    return {"request": f"An updated release of '{product}' … "
                       f"reflect what recently changed about {topic}."}
```

So a rebuild keeps the product's identity, and the curriculum revision knows
what it previously taught.

## Mechanics

`ComposedPipeline.prepare` names a hook that runs once, before any stage, and
seeds `acc` under `_prepared`. It is named rather than inlined because it does
I/O and therefore must run inside an activity — the workflow stays
deterministic, and the resulting `acc` seed comes back from the start activity
so the workflow can evaluate `skip_if` against it.

Both orchestration paths share this: the Temporal workflow and the inline
fallback evaluate the same predicates against the same prepared context.
