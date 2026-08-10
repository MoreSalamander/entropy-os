"""Typed configuration loader.

Single source of truth for runtime settings: `config/research.yaml` overlaid
with environment variables (env wins, so keys never need to live on disk).
Every module receives a Config object — nothing reads yaml directly.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from ...paths import RESEARCH_CONFIG, engine_storage

# Relative paths in the config file are this engine's own state, so they
# resolve inside the engine's storage rather than next to the source.
PROJECT_ROOT = engine_storage("research")


class LLMRoles(BaseModel):
    extract: str = "llama3.1:8b"
    plan: str = "llama3.1:8b"
    judge: str = "qwen3.5:9b"
    summarize: str = "qwen3.5-64k:latest"
    light: str = "llama3.2:latest"


class LLMConfig(BaseModel):
    base_url: str = "http://localhost:11434"
    roles: LLMRoles = Field(default_factory=LLMRoles)
    embed_model: str = "nomic-embed-text:latest"
    timeout_s: int = 120
    temperature: float = 0.0


class OrchestratorConfig(BaseModel):
    global_concurrency: int = 32
    per_source_concurrency: int = 3
    extract_concurrency: int = 3
    max_results_per_source: int = 8
    query_variants: int = 2


class Neo4jConfig(BaseModel):
    uri: str = "bolt://localhost:7687"
    user: str = "neo4j"
    password: str = ""


class GraphConfig(BaseModel):
    backend: str = "networkx"  # "networkx" | "neo4j"
    neo4j: Neo4jConfig = Field(default_factory=Neo4jConfig)


class VectorConfig(BaseModel):
    backend: str = "qdrant-embedded"
    path: str = "storage_data/qdrant"
    url: str = ""  # non-empty flips qdrant-client to server mode
    similarity_merge_threshold: float = 0.86


class DBConfig(BaseModel):
    url: str = "sqlite+aiosqlite:///storage_data/ledger.db"


class QueueConfig(BaseModel):
    backend: str = "asyncio"  # "asyncio" | "redis"
    redis_url: str = "redis://localhost:6379/0"


class KGConfig(BaseModel):
    path: str = "storage_data/knowledge_graph.json"


class SessionsConfig(BaseModel):
    path: str = "storage_data/sessions"


class DataHubConfig(BaseModel):
    enabled: str | bool = "auto"  # auto | true | false
    gms_url: str = "http://localhost:8080"
    platform: str = "research-engine"
    env: str = "PROD"


class SourceKeys(BaseModel):
    brave_search: str = ""
    serper: str = ""
    newsapi: str = ""
    ieee: str = ""
    patentsview: str = ""
    kaggle_username: str = ""
    kaggle_key: str = ""


class SourcesConfig(BaseModel):
    keys: SourceKeys = Field(default_factory=SourceKeys)
    reddit_degraded_ok: bool = True
    # An email address for the User-Agent this fleet presents. Empty by
    # default and deliberately not committed: Wikimedia requires a contact and
    # 403s without one, Crossref grants higher limits with one, and a public
    # repository is the wrong place to publish somebody's address. Set it in
    # RESEARCH_CONTACT (or here, on a private checkout).
    contact: str = ""


class ReportConfig(BaseModel):
    output_dir: str = "storage_data/reports"


class Config(BaseModel):
    llm: LLMConfig = Field(default_factory=LLMConfig)
    orchestrator: OrchestratorConfig = Field(default_factory=OrchestratorConfig)
    graph: GraphConfig = Field(default_factory=GraphConfig)
    vectors: VectorConfig = Field(default_factory=VectorConfig)
    db: DBConfig = Field(default_factory=DBConfig)
    queue: QueueConfig = Field(default_factory=QueueConfig)
    knowledge_graph: KGConfig = Field(default_factory=KGConfig)
    sessions: SessionsConfig = Field(default_factory=SessionsConfig)
    datahub: DataHubConfig = Field(default_factory=DataHubConfig)
    sources: SourcesConfig = Field(default_factory=SourcesConfig)
    report: ReportConfig = Field(default_factory=ReportConfig)

    def resolve_path(self, rel: str) -> Path:
        """Paths in config are project-root relative; absolute paths pass through."""
        p = Path(rel)
        return p if p.is_absolute() else PROJECT_ROOT / p


# Environment overrides: RESEARCH_ENGINE_<SECTION>__<FIELD> (double underscore
# nests), plus dedicated shortcuts for secrets so keys stay out of files.
_ENV_SHORTCUTS = {
    "BRAVE_SEARCH_API_KEY": ("sources", "keys", "brave_search"),
    "SERPER_API_KEY": ("sources", "keys", "serper"),
    "NEWSAPI_KEY": ("sources", "keys", "newsapi"),
    "IEEE_API_KEY": ("sources", "keys", "ieee"),
    "PATENTSVIEW_API_KEY": ("sources", "keys", "patentsview"),
    "KAGGLE_USERNAME": ("sources", "keys", "kaggle_username"),
    "KAGGLE_KEY": ("sources", "keys", "kaggle_key"),
    "RESEARCH_CONTACT": ("sources", "contact"),
    "NEO4J_PASSWORD": ("graph", "neo4j", "password"),
}


def _apply_env(data: dict[str, Any]) -> dict[str, Any]:
    for env_name, path in _ENV_SHORTCUTS.items():
        val = os.environ.get(env_name)
        if not val:
            continue
        node = data
        for key in path[:-1]:
            node = node.setdefault(key, {})
        node[path[-1]] = val
    return data


def load_config(path: str | Path | None = None) -> Config:
    """Load `config/research.yaml` by default, overlay env, return typed Config."""
    cfg_path = Path(path) if path else RESEARCH_CONFIG
    data: dict[str, Any] = {}
    if cfg_path.exists():
        data = yaml.safe_load(cfg_path.read_text()) or {}
    return Config.model_validate(_apply_env(data))
