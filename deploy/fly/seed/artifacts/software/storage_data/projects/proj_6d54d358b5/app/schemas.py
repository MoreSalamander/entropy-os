"""Pydantic schemas: every request validated, every response shaped."""

from datetime import datetime  # noqa: F401

from pydantic import BaseModel, ConfigDict


class HunterRunOutcomeCreate(BaseModel):
    hunter_run_id: str
    gate_outcome: str
    opportunity_type: str
    model_invoked: str
    created_at: datetime


class HunterRunOutcomeRead(HunterRunOutcomeCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int

class OpportunityCreate(BaseModel):
    hunter_run_id: str
    opportunity_type: str
    created_at: datetime


class OpportunityRead(OpportunityCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
