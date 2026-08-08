# Model backend — what actually runs the models

## The short version

one-engine itself makes **zero model calls**. It composes, gates, orchestrates,
and records. Every model call belongs to one of the four engines, and each
engine reaches its models through a four-method protocol:

```python
class LLMClient(Protocol):
    async def chat_json(role, system, user, schema) -> dict   # schema-constrained
    async def chat_text(role, system, user) -> str            # prose only
    async def embed(texts) -> list[list[float]]               # semantic search
    async def available() -> bool
```

Because that protocol is small, and because all four engine constructors accept
`llm: LLMClient | None`, the backend is selectable **without editing an
engine**. All four repositories remain byte-identical; the adapters pass a
client in.

## The default is local, and it is untouched

```
ONE_ENGINE_LLM_BACKEND=local        # the default
```

On the local backend `build_llm()` returns `None`, and each engine constructs
its own `OllamaClient` exactly as it always has — with its own tuned timeouts,
its own role→model routing, its own embed model. one-engine does not become the
owner of settings that belong to each engine.

Roles route to different local models on purpose, including **judge separation**:
the model that grades a claim is not the model that produced it.

| role | local model |
|---|---|
| extract, plan | `llama3.1:8b` |
| judge | `qwen3.5:9b` |
| summarize | `qwen3.5-64k` |
| light | `llama3.2` |
| embed | `nomic-embed-text` |

## The cloud backend

```
ONE_ENGINE_LLM_BACKEND=claude
ANTHROPIC_API_KEY=...               # read by the SDK; never copied into our objects
```

| variable | meaning |
|---|---|
| `ONE_ENGINE_CLAUDE_MODEL` | one model for every role (default `claude-opus-5`) |
| `ONE_ENGINE_CLAUDE_MODEL_JUDGE` | per-role override (also `_EXTRACT`, `_PLAN`, `_SUMMARIZE`, `_LIGHT`) |
| `ONE_ENGINE_CLAUDE_EFFORT` | `low`…`max`; unset uses the API default |
| `ONE_ENGINE_CLAUDE_FALLBACKS` | `0` disables server-side refusal fallback |
| `ONE_ENGINE_EMBED_URL` / `_MODEL` | where embeddings come from; empty disables them |

Every role defaults to the same model rather than a cheaper guess per role.
Which role deserves a cheaper model is a judgment about *your* cost/quality
tradeoff, so it is yours to make, not a default chosen on your behalf.

**Enabling this needs one install.** Adapters run inside each engine's own venv,
so the cloud backend requires `anthropic` there:

```bash
research-engine/.venv/bin/pip install anthropic   # and the other three
```

Until then, selecting `claude` still works — it fails at the first model call
with a message naming this exact fix, rather than crashing engine construction.

## Three things this backend has to get right

### 1. `chat_json` stays schema-constrained

The engines' design law is that the model only ever **proposes**, and a
deterministic validator decides. Ollama enforces the JSON schema server-side via
its `format` parameter. The Anthropic equivalent is structured outputs
(`output_config.format`), so the guarantee survives the move. Dropping to
"please reply in JSON" prose would quietly convert this system from constrained
output to hopeful output.

Anthropic's schema dialect is narrower than Ollama's — it rejects numeric and
string constraints and requires `additionalProperties: false`. Schemas are
therefore adapted on the way out, and the adaptation is **lossy in one direction
only**: constraints may be dropped, never invented. A schema that gained a rule
the engine never wrote would change what the model is allowed to propose.

### 2. A refusal is not a crash

Claude Opus 5 runs safety classifiers that can decline a request, returning
HTTP 200 with `stop_reason: "refusal"`. Research topics are arbitrary user text,
so this is live rather than theoretical. It is translated into `LLMUnavailable`
— the same signal a down provider raises — because the engines already degrade
honestly on that, and must never receive a refusal as though it were content.

Server-side fallbacks are on by default, so a topic that trips a classifier gets
re-served by another model inside the same call instead of taking a multi-stage
composed run down with it. If the account lacks that beta, the client notices
once and stops asking.

### 3. Embeddings are a separate axis

**The Anthropic API publishes no embeddings endpoint.** Its documented surface is
Messages, Batches, Files, Token Counting and Models; there is no embeddings route
and no embedding model in the catalog. But every engine hands its LLM client to a
`VectorIndex` that calls `embed()` for semantic entity resolution.

So "run this on Claude" cannot mean "run everything on Claude". It means chat on
Claude and embeddings somewhere else — normally the local `nomic-embed-text` that
is already there, costs nothing, and never needed to move. That is why the cloud
backend is a `HybridClient` composed of two backends rather than one class
pretending to be one.

If embeddings are unavailable, `embed()` raises `LLMUnavailable` and the engines
fall back to exact-match entity resolution — a path they already have. Returning
zero vectors instead would silently corrupt semantic search with confident
nonsense.

## Bring your own — what is easy and what is a tunnel

Backend selection is a **per-run value**, not a process-wide switch:

```python
build_llm(spec_from_env())              # the deployment's default
build_llm(spec_from_env().with_key(k))  # this one run, this one credential
```

That distinction is what makes a hosted deployment able to serve one visitor's
choice without changing the next visitor's run. Two versions of "bring your own"
follow from it, and they are **not** the same size of problem.

### Bring your own API key — small

The visitor supplies a key; the server uses it for that run and never persists
it. `LLMSpec.with_key()` already returns a scoped copy that does not mutate the
process default, and `describe()` never renders a credential. What remains is a
request field and a UI, plus the operational discipline that the key is never
logged, never written to the event log, and never stored.

It is worth being clear-eyed that this asks a stranger to paste a credential into
someone else's server. That is a normal pattern, but it should be stated plainly
on the page rather than implied.

### Bring your own Ollama — a tunnel, not a setting

The obstacle is not configuration, it is topology:

- The **browser** can reach the visitor's `http://localhost:11434`.
- The **server** cannot. The server's localhost is the server.

And the engines run server-side. So a hosted composed run cannot dial a
visitor's Ollama directly, no matter what is configured. Making it work means
the server asks the *browser* to make each model call on its behalf: a WebSocket
relay where the server sends `{role, system, user, schema}` and the browser
returns the completion from its own machine.

That is genuinely buildable, and the four-method protocol is exactly why it is
small — a relay client is the same shape as the Claude client. The real costs are
honest ones:

- The visitor must allow the site's origin: `OLLAMA_ORIGINS=https://<site>`.
  Ollama rejects cross-origin browser requests by default.
- Browser behaviour for an HTTPS page fetching `http://localhost` varies —
  `localhost` is treated as a trustworthy origin in some browsers and blocked in
  others. **This has not been tested here**, and should be verified per browser
  before being promised.
- The tab becomes infrastructure. A composed four-engine objective ran 42
  minutes; a relayed run stalls the moment the tab closes.

That last point suggests the natural fit: BYO-Ollama suits **single atomic
capabilities** — one research stage, one page of copy — rather than a full
multi-stage objective. Which lines up with the one-or-all design already in
place: atomic capabilities are exactly what a browser-relayed visitor can afford
to run.
