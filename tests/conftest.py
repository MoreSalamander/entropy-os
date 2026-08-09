"""Shared test fixtures for the front door.

The wedge reaches engines through the Universal Engine Contract, so a test of
the FRONT DOOR — auth, tenancy, metering, status mapping — needs an engine on
the other end that answers instantly and predictably. Without one, these tests
either wait minutes for a real generation or fail because a laptop happens not
to be running the composite, and in both cases they stop testing the thing
they are named after.
"""

from __future__ import annotations

from typing import Any

import pytest


def contract_result(*, status: str = "completed", accepted: bool = True,
                    outputs: dict[str, Any] | None = None,
                    artifacts: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """An ExecuteResult in the shape the contract client returns.

    `accepted` is a convenience over the real mechanism, not a substitute for
    it: it decides whether the single HARD verdict passed, and the acceptance
    rule still does the deciding from there.
    """
    return {
        "status": status,
        "outputs": dict(outputs or {}),
        "artifacts": list(artifacts or []),
        "verdicts": [{
            "gate": "pytest",
            "determinism": "hard",
            "passed": accepted,
            "evidence": "2 passed" if accepted else "1 failed",
            "facts": {},
        }],
        "provenance": {"ref": {"execution_id": "exec-test"}},
        "error": "" if status == "completed" else "the engine gave up",
    }


def fake_execute(accepted: bool = True):
    """A stand-in for the contract client: one capability call, one result."""
    def _execute(capability: str, inputs: dict[str, Any]) -> dict[str, Any]:
        return contract_result(accepted=accepted)
    return _execute


@pytest.fixture
def execute_ok():
    return fake_execute(True)


@pytest.fixture
def execute_rejected():
    return fake_execute(False)
