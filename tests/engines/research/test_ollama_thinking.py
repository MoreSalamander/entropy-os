"""Thinking stays off, and the payload says so.

The cost of leaving this to the model's default was not a slow answer, it was
a request that never returned: an established connection, no output, and
Ollama's runner idling until its keep-alive expired. The quieter version of
the same fault is an empty string coming back, which is why every research
report in storage has a blank Executive Summary.

Omitting `think` is not neutral — Ollama then does whatever the model
prefers, and a reasoning model prefers to think. So the field is asserted
rather than assumed.
"""

from __future__ import annotations

import pytest

from entropy_os.engines.research.config import LLMConfig
from entropy_os.engines.research.llm.client import OllamaClient


class Capture:
    """Stands in for the HTTP client and records what was sent."""

    def __init__(self, content: str = "ok"):
        self.sent: dict = {}
        self._content = content

    async def post(self, path, json=None, **kw):
        self.sent = {"path": path, "payload": json}

        class R:
            status_code = 200

            @staticmethod
            def raise_for_status():
                return None

            # Valid JSON, so the structured path parses it and the test is
            # about the payload rather than about the reply.
            @staticmethod
            def json():
                return {"message": {"content": "{}"}}
        return R()


@pytest.fixture
def client():
    c = OllamaClient(LLMConfig())
    c._client = Capture()
    return c


async def test_chat_text_sends_think_false(client):
    await client.chat_text("summarize", "sys", "user")
    assert client._client.sent["payload"]["think"] is False


async def test_chat_json_sends_think_false(client):
    """Structured extraction is the highest-volume call in a research run and
    the one that hung. It wants the object, never the reasoning."""
    await client.chat_json("extract", "sys", "user", {"type": "object"})
    assert client._client.sent["payload"]["think"] is False


async def test_the_field_is_present_not_merely_falsy(client):
    """`think` absent and `think: false` are different instructions to Ollama.
    Absent means "model's choice", which is the bug."""
    await client.chat_text("plan", "sys", "user")
    assert "think" in client._client.sent["payload"]


@pytest.mark.parametrize("role", ["extract", "plan", "judge", "summarize", "light"])
async def test_every_role_answers_directly(client, role):
    """One role left thinking on would fail exactly like the others did, and
    only on the runs that happened to use it."""
    await client.chat_text(role, "sys", "user")
    assert client._client.sent["payload"]["think"] is False
