"""Model backend selection: local by default, Claude on request, honest about
what the cloud cannot do.

The claims worth testing here are not "does Anthropic answer" — that needs a
credential and a network. They are the ones that decide whether this system
stays truthful when the backend moves: that the local path is left completely
alone, that a schema written for Ollama survives translation without gaining
constraints it never had, that a credential never reaches a log line, and that
the missing embeddings endpoint degrades instead of pretending.
"""

from __future__ import annotations

import pytest

from entropy_os.composition.llm import (
    ROLES,
    HybridClient,
    LLMSpec,
    RoutedClient,
    build_llm,
    describe_backend,
    spec_from_env,
)
from entropy_os.composition.llm.claude import LLMUnavailable, adapt_schema

# --------------------------------------------------------------------------- #
# selection — local stays untouched
# --------------------------------------------------------------------------- #

def test_the_default_backend_injects_nothing(monkeypatch):
    """The local path must remain exactly what the engines already do. Passing
    None means the engine constructs its own client with its own tuned
    timeouts and role routing — one-engine does not quietly become the owner
    of settings that belong to each engine."""
    monkeypatch.delenv("ONE_ENGINE_LLM_BACKEND", raising=False)
    assert build_llm() is None
    assert spec_from_env().backend == "local"


def test_an_unrecognized_backend_falls_back_to_local(monkeypatch):
    """A typo in a deployment env var must not silently route a run to a
    backend nobody chose."""
    monkeypatch.setenv("ONE_ENGINE_LLM_BACKEND", "claud")
    assert spec_from_env().backend == "local"
    assert build_llm() is None


def test_selecting_claude_produces_a_hybrid_client():
    """Chat and embeddings are separate axes, so the cloud backend is honestly
    two backends rather than one class pretending otherwise."""
    client = build_llm(LLMSpec(backend="claude"))
    assert isinstance(client, HybridClient)


def test_selection_works_without_the_sdk_installed():
    """`anthropic` is not installed in this environment, and selecting the
    cloud backend still succeeds. That is the point: a missing package must
    surface as LLMUnavailable at the first model call — where every engine
    already degrades — not as an exception during engine construction that
    takes the adapter down before it can do any deterministic work."""
    client = build_llm(LLMSpec(backend="claude"))
    assert isinstance(client, HybridClient)
    # Constructed, but nothing was imported or dialled to get here.
    assert client._chat._sdk is None


def test_backend_selection_is_per_run_not_per_process(monkeypatch):
    """A hosted deployment serves one visitor's choice without changing the
    next visitor's run, so an explicit spec must beat the environment."""
    monkeypatch.setenv("ONE_ENGINE_LLM_BACKEND", "local")
    assert build_llm() is None
    assert isinstance(build_llm(LLMSpec(backend="claude")), HybridClient)


# --------------------------------------------------------------------------- #
# per-role routing — judge to the cloud, the rest stays home
# --------------------------------------------------------------------------- #

def test_only_the_named_role_goes_to_the_cloud(monkeypatch):
    monkeypatch.setenv("ONE_ENGINE_CLAUDE_ROLES", "judge")
    spec = spec_from_env()
    assert spec.routes_to_cloud("judge") is True
    assert spec.routes_to_cloud("extract") is False
    assert spec.is_mixed is True


def test_a_mistyped_role_is_dropped_rather_than_silently_routing_nothing(
        monkeypatch):
    """A typo must not look configured. `judgement` is not a role, so it is
    discarded — and the run stays fully local rather than appearing to route."""
    monkeypatch.setenv("ONE_ENGINE_CLAUDE_ROLES", "judgement")
    spec = spec_from_env()
    assert spec.cloud_roles == frozenset()
    assert spec.any_cloud is False
    assert build_llm(spec) is None


def test_a_mixed_run_builds_both_halves():
    spec = LLMSpec(cloud_roles=frozenset({"judge"}))
    client = build_llm(spec, local=_StubChat)
    assert isinstance(client, RoutedClient)


def test_routing_all_roles_is_not_treated_as_mixed():
    """Naming every role is the same request as backend=claude, and must not
    drag in a local chat client nothing would use."""
    spec = LLMSpec(cloud_roles=frozenset(ROLES))
    assert spec.is_mixed is False
    assert isinstance(build_llm(spec), HybridClient)


@pytest.mark.asyncio
async def test_the_judge_call_goes_to_the_cloud_and_extraction_stays_local():
    """The point of the whole feature: the model that grades a claim can be a
    stronger one than the model that produced it, across providers."""
    local, cloud = _StubChat("local"), _StubChat("cloud")
    client = RoutedClient(local, cloud, LLMSpec(cloud_roles=frozenset({"judge"})))

    await client.chat_json("judge", "s", "u", {})
    await client.chat_json("extract", "s", "u", {})
    await client.chat_text("summarize", "s", "u")

    assert cloud.calls == ["json:judge"]
    assert local.calls == ["json:extract", "text:summarize"]


@pytest.mark.asyncio
async def test_embeddings_never_leave_the_local_half():
    """The cloud half has no embeddings endpoint at all, so routing a role
    there must never drag vectors along with it."""
    local, cloud = _StubChat("local"), _StubChat("cloud")
    local.embed = _StubEmbedder().embed
    client = RoutedClient(local, cloud, LLMSpec(cloud_roles=frozenset({"judge"})))
    assert len(await client.embed(["a"])) == 1
    assert cloud.calls == []


def test_a_mixed_spec_describes_both_sides_without_the_key():
    spec = LLMSpec(cloud_roles=frozenset({"judge"})).with_key("sk-ant-xyz")
    described = spec.describe()
    assert "judge" in described
    assert "sk-ant" not in described


# --------------------------------------------------------------------------- #
# credentials — never in a log line, never shared between runs
# --------------------------------------------------------------------------- #

def test_a_supplied_key_never_appears_in_the_description():
    spec = LLMSpec().with_key("sk-ant-secret-value")
    described = spec.describe()
    assert "secret" not in described
    assert "sk-ant" not in described
    assert "caller-supplied key" in described


def test_supplying_a_key_does_not_mutate_the_shared_spec():
    """One run's credential must not leak into the default every later run
    starts from."""
    base = LLMSpec()
    scoped = base.with_key("sk-ant-abc")
    assert base.claude_api_key == ""
    assert base.backend == "local"
    assert scoped.claude_api_key == "sk-ant-abc"
    assert scoped.backend == "claude"


def test_the_env_spec_does_not_copy_the_key_into_our_own_object(monkeypatch):
    """The SDK resolves the credential itself. Reading it into a dataclass
    would put it in tracebacks and repr() output for no benefit."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-from-env")
    monkeypatch.setenv("ONE_ENGINE_LLM_BACKEND", "claude")
    spec = spec_from_env()
    assert spec.claude_api_key == ""
    assert "sk-ant-from-env" not in repr(spec)
    assert "sk-ant-from-env" not in describe_backend(spec)


# --------------------------------------------------------------------------- #
# role routing — judge separation survives the move to the cloud
# --------------------------------------------------------------------------- #

def test_roles_are_addressable_so_judge_separation_can_be_preserved(monkeypatch):
    """Locally, the model that grades a claim is deliberately not the model
    that produced it. That separation is a property of the thesis, so the
    cloud backend has to keep it expressible."""
    monkeypatch.setenv("ONE_ENGINE_CLAUDE_MODEL", "claude-sonnet-5")
    monkeypatch.setenv("ONE_ENGINE_CLAUDE_MODEL_JUDGE", "claude-opus-5")
    spec = spec_from_env()
    assert spec.model_for("extract") == "claude-sonnet-5"
    assert spec.model_for("judge") == "claude-opus-5"


def test_roles_default_to_one_model_rather_than_a_cheaper_guess():
    """Which role deserves a cheaper model is the operator's cost judgment,
    not a default chosen on their behalf."""
    spec = LLMSpec(backend="claude")
    assert len({spec.model_for(r) for r in
                ("extract", "plan", "judge", "summarize", "light")}) == 1


# --------------------------------------------------------------------------- #
# schema translation — Ollama's dialect is wider than Anthropic's
# --------------------------------------------------------------------------- #

def test_unsupported_constraints_are_dropped_not_forwarded():
    """Anthropic's structured outputs reject the numeric/string constraints
    Ollama ignores. Forwarding them yields a 400 that reads like an engine
    bug rather than a dialect difference."""
    adapted = adapt_schema({
        "type": "object",
        "properties": {
            "score": {"type": "integer", "minimum": 0, "maximum": 10},
            "name": {"type": "string", "minLength": 1, "maxLength": 80},
        },
    })
    assert "minimum" not in adapted["properties"]["score"]
    assert "maxLength" not in adapted["properties"]["name"]
    assert adapted["properties"]["score"]["type"] == "integer"


def test_translation_is_lossy_in_one_direction_only():
    """Constraints may be dropped; none may be invented. A schema that gains a
    rule the engine never wrote would change what the model is allowed to
    propose."""
    original = {"type": "object", "properties": {"a": {"type": "string"}}}
    adapted = adapt_schema(original)
    invented = set(adapted["properties"]["a"]) - set(original["properties"]["a"])
    assert not invented


def test_objects_are_closed_as_structured_outputs_require():
    adapted = adapt_schema({"type": "object",
                            "properties": {"a": {"type": "string"}}})
    assert adapted["additionalProperties"] is False
    assert adapted["required"] == ["a"]


def test_an_explicit_required_list_is_respected():
    """Adding a field to `required` that the engine left optional would make
    the model fabricate a value to satisfy the schema."""
    adapted = adapt_schema({
        "type": "object",
        "properties": {"a": {"type": "string"}, "b": {"type": "string"}},
        "required": ["a"],
    })
    assert adapted["required"] == ["a"]


def test_nested_structures_are_translated_all_the_way_down():
    adapted = adapt_schema({
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "minItems": 1,
                "items": {"type": "object",
                          "properties": {"n": {"type": "integer",
                                               "minimum": 1}}},
            },
        },
    })
    items = adapted["properties"]["items"]
    assert "minItems" not in items
    assert items["items"]["additionalProperties"] is False
    assert "minimum" not in items["items"]["properties"]["n"]


def test_union_branches_are_translated_too():
    adapted = adapt_schema({
        "anyOf": [{"type": "object", "properties": {"a": {"type": "string"}}},
                  {"type": "string", "maxLength": 5}],
    })
    assert adapted["anyOf"][0]["additionalProperties"] is False
    assert "maxLength" not in adapted["anyOf"][1]


# --------------------------------------------------------------------------- #
# embeddings — the cloud backend does not have them, and says so
# --------------------------------------------------------------------------- #

class _StubChat:
    """Stands in for a chat backend; asserts routing without a network."""

    def __init__(self, name: str = "stub"):
        self.name = name
        self.calls: list[str] = []

    async def available(self) -> bool:
        return True

    async def chat_json(self, role, system, user, schema):
        self.calls.append(f"json:{role}")
        return {"ok": True}

    async def chat_text(self, role, system, user):
        self.calls.append(f"text:{role}")
        return "prose"

    async def embed(self, texts):
        raise AssertionError("chat backend must never serve embeddings")


class _StubEmbedder:
    async def embed(self, texts):
        return [[0.5] * 4 for _ in texts]


@pytest.mark.asyncio
async def test_chat_goes_to_one_backend_and_embeddings_to_the_other():
    chat = _StubChat()
    client = HybridClient(chat, _StubEmbedder())

    assert await client.chat_json("judge", "s", "u", {}) == {"ok": True}
    assert await client.chat_text("summarize", "s", "u") == "prose"
    vectors = await client.embed(["a", "b"])

    assert chat.calls == ["json:judge", "text:summarize"]
    assert len(vectors) == 2


@pytest.mark.asyncio
async def test_disabled_embeddings_degrade_rather_than_fabricate():
    """The engines catch LLMUnavailable and fall back to exact-match entity
    resolution. Returning zero vectors instead would silently corrupt semantic
    search with confident nonsense."""
    client = HybridClient(_StubChat(), None)
    with pytest.raises(LLMUnavailable) as e:
        await client.embed(["a"])
    assert "exact match" in str(e.value)


@pytest.mark.asyncio
async def test_availability_tracks_chat_not_embeddings():
    """Embeddings are optional by design; reporting the backend down because a
    local embedder is missing would refuse work that can actually be done."""
    assert await HybridClient(_StubChat(), None).available() is True
