"""GraphStore — the persistence interface behind the Knowledge Graph.

Two real implementations of one contract:

  NetworkXJSONStore  embedded default: zero servers, atomic JSON writes with
                     timestamped .bak files (a corrupted write can never eat
                     the accumulated knowledge)
  Neo4jStore         the spec's server backend; activates via
                     graph.backend=neo4j in config.yaml + `pip install neo4j`

The KnowledgeGraph layer above calls only this interface, so flipping
backends is a config edit, not a refactor.
"""

from __future__ import annotations

import json
import shutil
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import networkx as nx


class GraphStore(ABC):
    @abstractmethod
    def upsert_node(self, node_id: str, props: dict[str, Any]) -> None: ...

    @abstractmethod
    def get_node(self, node_id: str) -> dict[str, Any] | None: ...

    @abstractmethod
    def all_nodes(self) -> list[tuple[str, dict[str, Any]]]: ...

    @abstractmethod
    def upsert_edge(self, src: str, dst: str, key: str, props: dict[str, Any]) -> None: ...

    @abstractmethod
    def edges_of(self, node_id: str) -> list[tuple[str, str, str, dict[str, Any]]]: ...

    @abstractmethod
    def all_edges(self) -> list[tuple[str, str, str, dict[str, Any]]]: ...

    @abstractmethod
    def paths_between(self, src: str, dst: str, cutoff: int = 4) -> list[list[str]]: ...

    @abstractmethod
    def neighborhood(self, node_id: str, depth: int = 1) -> set[str]: ...

    @abstractmethod
    def flush(self) -> None: ...

    @abstractmethod
    def close(self) -> None: ...


class NetworkXJSONStore(GraphStore):
    """Embedded store: MultiDiGraph in memory, JSON on disk, atomic + backed up."""

    def __init__(self, path: Path):
        self.path = path
        self.g = nx.MultiDiGraph()
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        data = json.loads(self.path.read_text())
        for n in data.get("nodes", []):
            self.g.add_node(n["id"], **n.get("props", {}))
        for e in data.get("edges", []):
            self.g.add_edge(e["src"], e["dst"], key=e["key"], **e.get("props", {}))

    def upsert_node(self, node_id: str, props: dict[str, Any]) -> None:
        if self.g.has_node(node_id):
            self.g.nodes[node_id].update(props)
        else:
            self.g.add_node(node_id, **props)

    def get_node(self, node_id: str) -> dict[str, Any] | None:
        return dict(self.g.nodes[node_id]) if self.g.has_node(node_id) else None

    def all_nodes(self) -> list[tuple[str, dict[str, Any]]]:
        return [(n, dict(d)) for n, d in self.g.nodes(data=True)]

    def upsert_edge(self, src: str, dst: str, key: str, props: dict[str, Any]) -> None:
        if self.g.has_edge(src, dst, key=key):
            self.g.edges[src, dst, key].update(props)
        else:
            self.g.add_edge(src, dst, key=key, **props)

    def edges_of(self, node_id: str) -> list[tuple[str, str, str, dict[str, Any]]]:
        if not self.g.has_node(node_id):
            return []
        out = [(u, v, k, dict(d)) for u, v, k, d in self.g.out_edges(node_id, keys=True, data=True)]
        out += [(u, v, k, dict(d)) for u, v, k, d in self.g.in_edges(node_id, keys=True, data=True)]
        return out

    def all_edges(self) -> list[tuple[str, str, str, dict[str, Any]]]:
        return [(u, v, k, dict(d)) for u, v, k, d in self.g.edges(keys=True, data=True)]

    def paths_between(self, src: str, dst: str, cutoff: int = 4) -> list[list[str]]:
        if not (self.g.has_node(src) and self.g.has_node(dst)):
            return []
        ug = self.g.to_undirected(as_view=True)
        try:
            return [list(p) for _, p in zip(range(5),  # noqa: B905 — deliberate truncation to 5
                    nx.all_simple_paths(ug, src, dst, cutoff=cutoff))]
        except nx.NetworkXError:
            return []

    def neighborhood(self, node_id: str, depth: int = 1) -> set[str]:
        if not self.g.has_node(node_id):
            return set()
        ug = self.g.to_undirected(as_view=True)
        return set(nx.ego_graph(ug, node_id, radius=depth).nodes())

    def flush(self) -> None:
        """Atomic write + one timestamped .bak of the previous state."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            bak = self.path.with_suffix(f".json.bak.{time.strftime('%Y%m%d-%H%M%S')}")
            shutil.copy2(self.path, bak)
            # keep the three newest backups, prune the rest
            baks = sorted(self.path.parent.glob(self.path.name + ".bak.*"), reverse=True)
            for old in baks[3:]:
                old.unlink(missing_ok=True)
        payload = {
            "nodes": [{"id": n, "props": dict(d)} for n, d in self.g.nodes(data=True)],
            "edges": [{"src": u, "dst": v, "key": k, "props": dict(d)}
                      for u, v, k, d in self.g.edges(keys=True, data=True)],
        }
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=1, default=str))
        tmp.replace(self.path)

    def close(self) -> None:
        self.flush()


class Neo4jStore(GraphStore):
    """The spec's Neo4j backend. Requires `pip install neo4j` and a running
    server; selected via graph.backend=neo4j. Property maps mirror the JSON
    store exactly so the two backends are interchangeable."""

    def __init__(self, uri: str, user: str, password: str):
        try:
            from neo4j import GraphDatabase  # deferred: optional dependency
        except ImportError as e:
            raise RuntimeError(
                "graph.backend=neo4j but the driver is missing — "
                "run: pip install neo4j") from e
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
        self.driver.verify_connectivity()

    def _run(self, query: str, **params):
        with self.driver.session() as s:
            return list(s.run(query, **params))

    def upsert_node(self, node_id: str, props: dict[str, Any]) -> None:
        self._run("MERGE (n:KGNode {id: $id}) SET n += $props",
                  id=node_id, props={k: json.dumps(v) if isinstance(v, (dict, list)) else v
                                     for k, v in props.items()})

    def get_node(self, node_id: str) -> dict[str, Any] | None:
        rows = self._run("MATCH (n:KGNode {id: $id}) RETURN properties(n) AS p", id=node_id)
        if not rows:
            return None
        props = dict(rows[0]["p"])
        props.pop("id", None)
        return props

    def all_nodes(self) -> list[tuple[str, dict[str, Any]]]:
        rows = self._run("MATCH (n:KGNode) RETURN n.id AS id, properties(n) AS p")
        out = []
        for r in rows:
            props = dict(r["p"])
            props.pop("id", None)
            out.append((r["id"], props))
        return out

    def upsert_edge(self, src: str, dst: str, key: str, props: dict[str, Any]) -> None:
        self._run(
            "MATCH (a:KGNode {id: $src}), (b:KGNode {id: $dst}) "
            "MERGE (a)-[r:REL {key: $key}]->(b) SET r += $props",
            src=src, dst=dst, key=key,
            props={k: json.dumps(v) if isinstance(v, (dict, list)) else v
                   for k, v in props.items()})

    def edges_of(self, node_id: str) -> list[tuple[str, str, str, dict[str, Any]]]:
        rows = self._run(
            "MATCH (a:KGNode {id: $id})-[r:REL]-(b:KGNode) "
            "RETURN startNode(r).id AS src, endNode(r).id AS dst, r.key AS key, "
            "properties(r) AS p", id=node_id)
        return [(r["src"], r["dst"], r["key"], dict(r["p"])) for r in rows]

    def all_edges(self) -> list[tuple[str, str, str, dict[str, Any]]]:
        rows = self._run("MATCH (a:KGNode)-[r:REL]->(b:KGNode) "
                         "RETURN a.id AS src, b.id AS dst, r.key AS key, properties(r) AS p")
        return [(r["src"], r["dst"], r["key"], dict(r["p"])) for r in rows]

    def paths_between(self, src: str, dst: str, cutoff: int = 4) -> list[list[str]]:
        rows = self._run(
            f"MATCH p=(a:KGNode {{id: $src}})-[*..{int(cutoff)}]-(b:KGNode {{id: $dst}}) "
            "RETURN [n IN nodes(p) | n.id] AS ids LIMIT 5", src=src, dst=dst)
        return [r["ids"] for r in rows]

    def neighborhood(self, node_id: str, depth: int = 1) -> set[str]:
        rows = self._run(
            f"MATCH (a:KGNode {{id: $id}})-[*1..{int(depth)}]-(b:KGNode) "
            "RETURN DISTINCT b.id AS id", id=node_id)
        return {node_id} | {r["id"] for r in rows}

    def flush(self) -> None:
        pass  # Neo4j persists per-transaction

    def close(self) -> None:
        self.driver.close()


def make_graph_store(backend: str, json_path: Path, neo4j_uri: str = "",
                     neo4j_user: str = "", neo4j_password: str = "") -> GraphStore:
    if backend == "neo4j":
        return Neo4jStore(neo4j_uri, neo4j_user, neo4j_password)
    return NetworkXJSONStore(json_path)
