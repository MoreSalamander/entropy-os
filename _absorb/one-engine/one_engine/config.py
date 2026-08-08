"""System topology loader for one-engine.

Reads config.yaml at the repo root. Kept as plain dataclasses (not pydantic)
because this is operator configuration, not contract surface — the contract
must stay independent of how any particular deployment wires its members.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent


@dataclass
class MemberConfig:
    name: str
    repo: str = ""
    venv: str = ""
    port: int = 0
    url: str = ""


@dataclass
class SystemConfig:
    engines: dict[str, MemberConfig] = field(default_factory=dict)
    unified_name: str = "one-engine"
    unified_port: int = 9100
    unified_url: str = "http://localhost:9100"
    unified_platform: str = "one-engine"
    system_b_name: str = "meta-studio"
    system_b_port: int = 9200
    datahub_gms: str = "http://localhost:8080"
    datahub_env: str = "PROD"
    temporal_address: str = "localhost:7233"
    temporal_namespace: str = "default"
    temporal_task_queue: str = "one-engine-objectives"
    events_log_path: Path = REPO_ROOT / "storage_data" / "events.jsonl"


def load_config(path: Path | None = None) -> SystemConfig:
    """Load config.yaml, then let the environment override every address.

    The file describes a laptop; a deployment describes itself. Members are
    addressed by URL, so moving this system onto separate hosts is a matter of
    changing addresses and nothing else — which is only true if the addresses
    are not baked in. Environment wins over file, per key:

        ONE_ENGINE_MEMBER_RESEARCH   member URL (…_SOFTWARE, _UNIVERSITY, _WEB)
        ONE_ENGINE_UNIFIED_URL       the composite's own public address
        ONE_ENGINE_PORT              the port the composite listens on
        DATAHUB_GMS                  metadata backbone
        TEMPORAL_ADDRESS             durable orchestrator
        ONE_ENGINE_DATA              writable root for the event log

    Anything unset falls back to the file, so a laptop needs no environment at
    all and a deployment needs no edited file.
    """
    raw = yaml.safe_load((path or REPO_ROOT / "config.yaml").read_text())
    cfg = SystemConfig()
    for name, e in (raw.get("engines") or {}).items():
        cfg.engines[name] = MemberConfig(
            name=name, repo=e.get("repo", ""), venv=e.get("venv", ""),
            port=int(e.get("port", 0)),
            url=os.environ.get(f"ONE_ENGINE_MEMBER_{name.upper()}",
                               e.get("url", "")))
    uni = raw.get("unified") or {}
    cfg.unified_name = uni.get("name", cfg.unified_name)
    cfg.unified_port = int(os.environ.get("ONE_ENGINE_PORT",
                                          uni.get("port", cfg.unified_port)))
    cfg.unified_url = os.environ.get("ONE_ENGINE_UNIFIED_URL",
                                     uni.get("url", cfg.unified_url))
    cfg.unified_platform = uni.get("datahub_platform", cfg.unified_platform)
    sb = raw.get("system_b") or {}
    cfg.system_b_name = sb.get("name", cfg.system_b_name)
    cfg.system_b_port = int(os.environ.get("ONE_ENGINE_SYSTEM_B_PORT",
                                           sb.get("port", cfg.system_b_port)))
    dh = raw.get("datahub") or {}
    cfg.datahub_gms = os.environ.get("DATAHUB_GMS",
                                     dh.get("gms_url", cfg.datahub_gms))
    cfg.datahub_env = dh.get("env", cfg.datahub_env)
    tp = raw.get("temporal") or {}
    cfg.temporal_address = os.environ.get(
        "TEMPORAL_ADDRESS", tp.get("address", cfg.temporal_address))
    cfg.temporal_namespace = os.environ.get(
        "TEMPORAL_NAMESPACE", tp.get("namespace", cfg.temporal_namespace))
    cfg.temporal_task_queue = os.environ.get(
        "TEMPORAL_TASK_QUEUE", tp.get("task_queue", cfg.temporal_task_queue))
    ev = raw.get("events") or {}
    if ev.get("log_path"):
        p = Path(ev["log_path"])
        cfg.events_log_path = p if p.is_absolute() else REPO_ROOT / p
    # A deployment's disk is not the repository's. ONE_ENGINE_DATA relocates
    # the durable event log to wherever the host actually gives us to write —
    # a mounted volume, rather than an image layer that vanishes on restart.
    if data_root := os.environ.get("ONE_ENGINE_DATA"):
        cfg.events_log_path = Path(data_root) / cfg.events_log_path.name
    return cfg
