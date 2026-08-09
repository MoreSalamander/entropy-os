"""Reading DataHub before deciding — the direction this system never had.

Everything here has always emitted INTO the metadata graph: gate verdicts as
assertions, runs as datasets, stage handoffs as lineage. That makes the graph
a record. It does not make it an input, and a record nothing consults is a
diary rather than a memory.

This is the other direction. An agent asks DataHub what already exists —
which datasets are real, what fields they actually carry, what feeds what —
and uses the answer BEFORE it generates anything. The difference shows up in
the artifact: code written against a schema that was looked up cannot invent
a column, and code written against a guess routinely does.

Reached through DataHub's own MCP server (`mcp-server-datahub`), which is the
interface DataHub publishes for exactly this. Speaking its GraphQL directly
would have worked and would have been our own private shape; the point of a
published agent interface is that the next agent, ours or anyone's, asks the
same way.

**It degrades honestly.** When the server or the instance is unreachable,
every call returns an empty result carrying the reason, and a caller that
generates anyway must say it generated blind. Silence dressed as "no related
datasets" would be worse than an error: it reads as a searched graph that
happened to be empty.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

DEFAULT_GMS = "http://localhost:8080"
# A read against a local instance answers in well under a second; anything
# past this is a server that is not going to answer at all.
CALL_TIMEOUT_S = 45.0


class DataHubUnavailable(RuntimeError):
    """The graph could not be consulted. Never confused with 'nothing found'."""


@dataclass
class Field_:
    path: str
    type: str = ""
    description: str = ""


@dataclass
class Dataset:
    """One real dataset, as DataHub describes it."""
    urn: str
    name: str
    platform: str = ""
    fields: list[Field_] = field(default_factory=list)

    @property
    def is_described(self) -> bool:
        return bool(self.fields)


@dataclass
class GraphContext:
    """What the graph knew, and what it could not answer.

    `reason` is populated only when the consultation FAILED. A successful
    search that found nothing leaves it empty and `datasets` empty — the two
    states are different and a generator must be able to tell them apart.
    """
    query: str
    datasets: list[Dataset] = field(default_factory=list)
    upstreams: dict[str, list[str]] = field(default_factory=dict)
    reason: str = ""

    @property
    def consulted(self) -> bool:
        return not self.reason

    def brief(self) -> str:
        """The graph, as text a generator can be given.

        Deliberately plain: field paths and types, and what feeds what. No
        prose, nothing inferred — a model reading this should be unable to
        tell the difference between what DataHub said and what it said,
        because there is none.
        """
        if not self.consulted:
            return f"(DataHub was not consulted: {self.reason})"
        if not self.datasets:
            return "(DataHub was consulted and holds nothing related to this request)"
        out: list[str] = []
        for d in self.datasets:
            head = f"{d.name} [{d.platform}]"
            ups = self.upstreams.get(d.urn) or []
            if ups:
                head += f"  ← fed by {', '.join(u.split(',')[1] if ',' in u else u for u in ups[:4])}"
            out.append(head)
            for f in d.fields[:24]:
                t = f" : {f.type}" if f.type else ""
                out.append(f"    {f.path}{t}")
            if len(d.fields) > 24:
                out.append(f"    … {len(d.fields) - 24} more fields")
        return "\n".join(out)


def _text(result: Any) -> str:
    return "".join(c.text for c in getattr(result, "content", []) if hasattr(c, "text"))


def _loads(blob: str) -> Any:
    """MCP tools answer with text; the payload is the LAST JSON object in it.

    The server echoes the GraphQL it ran and then a `Variables: {...}` dict
    before the result. Both are useful to a human reading a transcript and
    both are valid JSON, so scanning forward returns the variables — a real
    object, with none of the fields asked for, which looks exactly like an
    empty graph. Scanning backwards returns the answer.
    """
    for i in range(len(blob) - 1, -1, -1):
        if blob[i] != "{":
            continue
        try:
            return json.loads(blob[i:])
        except json.JSONDecodeError:
            continue
    return {}


@asynccontextmanager
async def session(gms_url: str = ""):
    """An MCP session against DataHub, or DataHubUnavailable."""
    try:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
    except ImportError as e:      # the extra is not installed
        raise DataHubUnavailable(f"mcp client not installed: {e}") from e

    python = sys.executable or shutil.which("python3") or "python3"
    params = StdioServerParameters(
        command=python, args=["-m", "mcp_server_datahub"],
        env={**os.environ,
             "DATAHUB_GMS_URL": gms_url or os.environ.get("DATAHUB_GMS", DEFAULT_GMS)})
    try:
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as s:
                await s.initialize()
                yield s
    except DataHubUnavailable:
        raise
    except Exception as e:
        raise DataHubUnavailable(f"{type(e).__name__}: {e}") from e


async def consult(request: str, gms_url: str = "", limit: int = 4) -> GraphContext:
    """Ask the graph what it already knows about this request.

    Three questions, in the order a person would ask them: what exists, what
    shape is it, and where does it come from. Each is a real MCP call; none
    of it is cached, because a stale answer about a schema is exactly the
    kind of confident wrongness this is meant to prevent.
    """
    ctx = GraphContext(query=request)
    try:
        async with session(gms_url) as s:
            found = _loads(_text(await s.call_tool(
                "search", {"query": request, "num_results": limit})))
            results = found.get("searchResults") or []
            for r in results:
                ent = r.get("entity") or {}
                urn = ent.get("urn", "")
                if not urn:
                    continue
                name = ((ent.get("properties") or {}).get("name")
                        or (urn.split(",")[1] if "," in urn else urn))
                platform = (urn.split("dataPlatform:")[1].split(",")[0]
                            if "dataPlatform:" in urn else "")
                ctx.datasets.append(Dataset(urn=urn, name=name, platform=platform))

            for d in ctx.datasets:
                schema = _loads(_text(await s.call_tool(
                    "list_schema_fields", {"urn": d.urn, "limit": 60})))
                for f in (schema.get("fields") or schema.get("schemaFields") or []):
                    d.fields.append(Field_(
                        path=f.get("fieldPath") or f.get("path") or "",
                        type=str(f.get("type") or f.get("nativeDataType") or ""),
                        description=f.get("description") or ""))

                lin = _loads(_text(await s.call_tool(
                    "get_lineage", {"urn": d.urn, "upstream": True,
                                    "max_hops": 1, "max_results": 6})))
                ups = [e.get("urn") for e in (lin.get("relationships")
                                              or lin.get("entities") or [])
                       if isinstance(e, dict) and e.get("urn")]
                if ups:
                    ctx.upstreams[d.urn] = ups
    except DataHubUnavailable as e:
        ctx.reason = str(e)
    return ctx
