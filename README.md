# learn-engine

**AI-native Education Intelligence Platform** — fourth engine of the
MoreSalamander family, on the
[research-engine](https://github.com/MoreSalamander/research-engine) substrate.

State a learning goal. The platform builds a validated prerequisite roadmap,
researches every concept from live open sources, and runs an adaptive
teaching loop — lessons, Socratic dialogues, practice, assessment, spaced
review — against an **evidence-based learner model**. Mastery is computed,
never asserted.

```
Student Goal → Roadmap DAG → Parallel Educational Research
→ Student Context Graph → Education Knowledge Graph
→ Teaching Agent Organization → Adaptive Learning Engine
→ Practice + Assessment → Mastery Tracking → Shared Teaching Memory
```

## Quick start

```bash
python3 -m venv .venv
.venv/bin/pip install -e ../research-engine -e .
# requires Ollama running locally
.venv/bin/python -m learn_engine study "Teach me machine learning" --steps 3
# --auto simulates a learner (demos/pipelines); omit it to answer yourself
```

API: `.venv/bin/uvicorn learn_engine.api.app:app --port 8020` — sessions,
adaptive `/next`, graded `/answer` (reference answers never ship to the
client), and KG queries (`/knowledge/gaps`, `/knowledge/bridges`).

## The deterministic spine

- **Roadmap gate** — concepts deduped, relations vocabulary-checked,
  circular prerequisites broken with a note, learning order = topological
  sort (prerequisites first, deterministic tie-break).
- **Mastery rubric** (constants in `models.py`, tested):
  lesson → *introduced*; first correct → *practicing*; **mastered needs a
  3-streak spanning ≥2 item kinds** (breadth, not luck); two consecutive
  misses demote a level (never below introduced). LLM-judged free-text
  carries half weight — it can help, never single-handedly promote.
- **Spaced review** — due dates from fixed intervals per level (1d/3d/21d);
  overdue review outranks every other activity.
- **The code-executes gate** — generated Python exercises are executed in a
  sandboxed subprocess at generation time; the reference solution must
  reproduce the answer or the exercise is rejected. When the LLM's claimed
  output disagrees with execution, **execution wins**.
- **Adaptive policy** — a decision tree that always states its reason:
  overdue review → misconception repair (Socratic) → continue practicing →
  next concept in prerequisite order → done. Mastered concepts are never
  re-taught.

## The teaching organization

Teacher (evidence-grounded explanations) · Socratic (question chains with
hints, never answers) · Visualization (mermaid concept maps generated
deterministically from the graph) · Practice (gated generation) ·
Assessment (deterministic grading for MCQ/numeric/code; judge-model grading
for free text at half weight, different model family) · Research (6 parallel
agents: Academic/Explanation/Practical/Historical/Industry over arXiv,
OpenAlex, Semantic Scholar, Wikipedia, GitHub, HN, GDELT, Crossref + open
courseware fetches) · Curriculum (goal analysis + the adaptive policy).

## What the graphs remember

**Student Context Graph** (per session): current activity + stated reason,
confusion points, interactions, mastery snapshot. **Education Knowledge
Graph** (persistent): concepts and their relations across all subjects,
attached resources, the shared **misconception library**, and
explanation-outcome records — which teaching method actually precedes
success, per concept and per learner. Cross-disciplinary discovery walks
this graph (`/knowledge/bridges`).

## Honest constraints

- Sources are the open web (live keyless); no LMS integrations or paywalled
  courseware. Open-courseware coverage is best-effort page fetching.
- Mastery evidence comes only from graded interactions inside the system —
  no imported transcripts.
- Code practice is Python-only, `-I`-isolated subprocess, 5s timeout.
- Visualizations are mermaid + a static HTML lesson bundle.
- Method-effectiveness stats need ≥2 attempts before they steer anything.

## Tests

```bash
.venv/bin/python -m pytest   # 31 offline tests: rubric transitions, DAG
                             # gates, code-executes gate, grading, policy order
```
