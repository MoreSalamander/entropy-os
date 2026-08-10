"""Pydantic schemas: every request validated, every response shaped."""

from datetime import datetime  # noqa: F401

from pydantic import BaseModel, ConfigDict


class HunterRunCreate(BaseModel):
    hunter_id: str
    location: str
    timestamp: datetime


class HunterRunRead(HunterRunCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int

class GateOutcomeCreate(BaseModel):
    hunter_run_id: int
    gate_outcome: str


class GateOutcomeRead(GateOutcomeCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
