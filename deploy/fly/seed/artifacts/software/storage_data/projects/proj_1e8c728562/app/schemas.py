"""Pydantic schemas: every request validated, every response shaped."""

from datetime import datetime  # noqa: F401

from pydantic import BaseModel, ConfigDict


class StringReversalRequestCreate(BaseModel):
    input_string: str


class StringReversalRequestRead(StringReversalRequestCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int

class StringReversalResponseCreate(BaseModel):
    reversed_string: str


class StringReversalResponseRead(StringReversalResponseCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
