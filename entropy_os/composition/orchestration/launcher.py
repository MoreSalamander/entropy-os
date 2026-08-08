"""Temporal launcher — the composite's durable execution path.

Wired into CompositeEngine as its workflow_launcher when the cluster is
reachable. If the connection cannot be made at startup the composite keeps
its inline path instead: degraded, and provenance says so.
"""

from __future__ import annotations

from temporalio.client import Client
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.service import RPCError

from ..config import SystemConfig
from ..contract import ExecuteResult


class TemporalLauncher:
    def __init__(self, client: Client, task_queue: str):
        self.client = client
        self.task_queue = task_queue

    async def __call__(self, capability: str, inputs: dict,
                       objective_id: str) -> ExecuteResult:
        # workflow_id == objective_id: the objective IS the durable unit, so
        # a retried submission of the same objective attaches to the running
        # workflow rather than starting a second one.
        handle = await self.client.start_workflow(
            "ComposedObjective",
            args=[capability, inputs, objective_id],
            id=objective_id, task_queue=self.task_queue,
            # Started by NAME, so the SDK has no return type to infer;
            # without result_type the caller gets a bare dict back.
            result_type=ExecuteResult)
        return await handle.result()

    async def progress(self, objective_id: str) -> dict:
        handle = self.client.get_workflow_handle(objective_id)
        return await handle.query("progress")

    async def signal(self, objective_id: str, name: str,
                     note: str = "") -> None:
        handle = self.client.get_workflow_handle(objective_id)
        await handle.signal(name, note)


async def try_connect(cfg: SystemConfig) -> TemporalLauncher | None:
    """Best-effort connection. Returns None when Temporal is not running —
    the caller then keeps inline composition rather than failing to start."""
    try:
        client = await Client.connect(cfg.temporal_address,
                                      namespace=cfg.temporal_namespace,
                                      data_converter=pydantic_data_converter)
    except (RuntimeError, RPCError, OSError):
        return None
    return TemporalLauncher(client, cfg.temporal_task_queue)
