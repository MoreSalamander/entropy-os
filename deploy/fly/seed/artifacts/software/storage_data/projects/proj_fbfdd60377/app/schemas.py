"""Pydantic schemas: every request validated, every response shaped."""

from datetime import datetime  # noqa: F401

from pydantic import BaseModel, ConfigDict


class Opportunity1Create(BaseModel):
    accepted: bool | None = None
    accepted_because: str | None = None
    confidence: str | None = None
    created_by: str | None = None
    model_invoked: str | None = None
    retrieved_context: str | None = None
    type: str | None = None


class Opportunity1Read(Opportunity1Create):
    model_config = ConfigDict(from_attributes=True)

    id: int

class Opportunity3Create(BaseModel):
    accepted: bool | None = None
    accepted_because: str | None = None
    confidence: str | None = None
    created_by: str | None = None
    model_invoked: str | None = None
    retrieved_context: str | None = None
    type: str | None = None


class Opportunity3Read(Opportunity3Create):
    model_config = ConfigDict(from_attributes=True)

    id: int

class Opportunity0Create(BaseModel):
    accepted: bool | None = None
    accepted_because: str | None = None
    confidence: str | None = None
    created_by: str | None = None
    model_invoked: str | None = None
    retrieved_context: str | None = None
    type: str | None = None


class Opportunity0Read(Opportunity0Create):
    model_config = ConfigDict(from_attributes=True)

    id: int

class Opportunity2Create(BaseModel):
    accepted: bool | None = None
    accepted_because: str | None = None
    confidence: str | None = None
    created_by: str | None = None
    model_invoked: str | None = None
    retrieved_context: str | None = None
    type: str | None = None


class Opportunity2Read(Opportunity2Create):
    model_config = ConfigDict(from_attributes=True)

    id: int

class OpportunityCreate(BaseModel):
    accepted: bool
    accepted_because: str
    confidence: str
    created_by: str
    model_invoked: str
    retrieved_context: str
    type: str


class OpportunityRead(OpportunityCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
