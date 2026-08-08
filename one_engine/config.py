"""System topology loader for one-engine.

Reads config.yaml at the repo root. Kept as plain dataclasses (not pydantic)
because this is operator configuration, not contract surface — the contract
must stay independent of how any particular deployment wires its members.
"""

from __future__ import annotations

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
    raw = yaml.safe_load((path or REPO_ROOT / "config.yaml").read_text())
    cfg = SystemConfig()
    for name, e in (raw.get("engines") or {}).items():
        cfg.engines[name] = MemberConfig(name=name, repo=e.get("repo", ""),
                                         venv=e.get("venv", ""),
                                         port=int(e.get("port", 0)),
                                         url=e.get("url", ""))
    uni = raw.get("unified") or {}
    cfg.unified_name = uni.get("name", cfg.unified_name)
    cfg.unified_port = int(uni.get("port", cfg.unified_port))
    cfg.unified_url = uni.get("url", cfg.unified_url)
    cfg.unified_platform = uni.get("datahub_platform", cfg.unified_platform)
    sb = raw.get("system_b") or {}
    cfg.system_b_name = sb.get("name", cfg.system_b_name)
    cfg.system_b_port = int(sb.get("port", cfg.system_b_port))
    dh = raw.get("datahub") or {}
    cfg.datahub_gms = dh.get("gms_url", cfg.datahub_gms)
    cfg.datahub_env = dh.get("env", cfg.datahub_env)
    tp = raw.get("temporal") or {}
    cfg.temporal_address = tp.get("address", cfg.temporal_address)
    cfg.temporal_namespace = tp.get("namespace", cfg.temporal_namespace)
    cfg.temporal_task_queue = tp.get("task_queue", cfg.temporal_task_queue)
    ev = raw.get("events") or {}
    if ev.get("log_path"):
        p = Path(ev["log_path"])
        cfg.events_log_path = p if p.is_absolute() else REPO_ROOT / p
    return cfg
