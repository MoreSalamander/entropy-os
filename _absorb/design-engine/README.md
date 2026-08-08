# design-engine

**AI-native Website Intelligence and Generation Engine** — a MoreSalamander
StudioLabs production, built on the
[research-engine](https://github.com/MoreSalamander/research-engine) substrate
(engine on engine, installed editable).

Enter an idea. The engine analyzes intent, researches real websites in
parallel, extracts abstract design traits into a Context Graph, accumulates a
persistent Design Knowledge Graph (DataHub-emitted), synthesizes an original
design system behind deterministic gates, generates a complete
Next.js/React/TypeScript/Tailwind site, reviews it with five agents, improves
it automatically, and learns from the outcome.

```
User Idea → Intent Analysis → Parallel Web Intelligence (6 workers)
→ Design Context Graph → Design Knowledge Graph → Design Synthesis
→ Copywriting → Code Generation → Review Agents → Auto-Improve
→ Build Gate → Finished Website → Graph Memory Loop
```

## Quick start

```bash
python3 -m venv .venv
.venv/bin/pip install -e ../research-engine && .venv/bin/pip install -e .
# requires Ollama running locally
.venv/bin/python -m design_engine "Create a website for an AI healthcare startup" --build
```

The generated site is a standalone repo: `cd <out> && npm install && npm run dev`.

API: `.venv/bin/uvicorn design_engine.api.app:app --port 8018` —
`POST /generate`, `GET /projects/{id}`, `GET /graph/knowledge/stats`,
`GET /graph/knowledge/priors/{industry}`, `POST /projects/{id}/feedback`.

## How originality is enforced (not promised)

- The **SiteAnalyzer** is the copying boundary: fetched markup is reduced to
  abstract traits (palette roles, font classes, nav archetypes, section
  signals, motion volume, framework fingerprints) — nothing downstream ever
  sees a fetched site's HTML.
- The **synthesis LLM** receives only aggregate statistics (trait census,
  section priors, palette pools, KG industry priors) plus the intent.
- The **novelty gate** is math: a synthesized palette matching ≥3 of 5 roles
  of any single analyzed site is de-derived (deterministic hue rotation) or
  replaced; inspirations must cite ≥2 distinct sites. The check result ships
  in the design system's `novelty_note`.
- The **WCAG gate** is math too: text/background pairs are walked to AA
  contrast before any CSS is written, and the Accessibility agent recomputes
  from the shipped CSS.

## The 11-agent organization

| Agent | Phase | Mechanism |
|---|---|---|
| UX Research | research | award/SaaS seeds → section + conversion signals |
| Visual Design | research | award tier → typography/color/motion traits |
| Branding | research | startup/industry seeds → positioning traits |
| Competitor Analysis | research | HN keyless (+Brave/Serper keyed) discovery → live analysis |
| Industry Research | research | industry seeds + Wikipedia context |
| Frontend Architecture | research | GitHub component/template ecosystem |
| Copywriting | generation | schema-gated copy; real-brand personas scrubbed deterministically |
| Accessibility | review | contrast math, heading invariant, landmarks, labels, reduced-motion |
| Performance | review | SVG/CSS-only assets, swap fonts, dependency allowlist |
| Conversion (UX) | review | above-fold CTA, dead-link check, closing CTA |
| Quality Assurance | review | shared chrome, token discipline + `next build` compile gate |

(+ a Security reviewer: headers, no dangerous HTML, external-link rel, no
external form posts.)

## Honest constraints

- **No Awwwards/Dribbble API exists.** Award-tier coverage is a curated seed
  corpus of real flagship sites fetched and analyzed live; open-web discovery
  of new sites needs a Brave/Serper key (adapters ship fail-closed).
  Semantic-intent search runs over the engine's own analyzed corpus.
- **Codegen is deterministic-scaffold by design:** the LLM proposes tokens,
  plans, and copy through schema gates; a typed 16-component library renders
  the code. Local 8B models don't write production multi-file TS — the
  template system is what makes "production-quality" true.
- **Review is static analysis + compile gate**, not live Lighthouse.
- **The memory loop learns from review scores and human feedback** — it has
  no deployed-site analytics and fabricates no conversion data. Placeholder
  personas/logos/stats in generated sites are labeled as such.

## Tests

```bash
.venv/bin/python -m pytest   # 29 offline deterministic tests
```
