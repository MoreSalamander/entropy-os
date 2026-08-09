"""Pydantic schemas: every request validated, every response shaped."""

from datetime import datetime  # noqa: F401

from pydantic import BaseModel, ConfigDict


class HunterRunOutcomeCreate(BaseModel):
    hunter_run_id: int
    opportunity_type: str
    model_invoked: str
    outcome: bool


class HunterRunOutcomeRead(HunterRunOutcomeCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int

class OpportunityCreate(BaseModel):
    opportunity_type: str
    model_invoked: str


class OpportunityRead(OpportunityCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
