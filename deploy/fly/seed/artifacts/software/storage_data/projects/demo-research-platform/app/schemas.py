"""Pydantic schemas: every request validated, every response shaped."""

from datetime import datetime  # noqa: F401

from pydantic import BaseModel, ConfigDict


class UserCreate(BaseModel):
    username: str
    email: str


class UserRead(UserCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int

class DatasetCreate(BaseModel):
    title: str
    description: str


class DatasetRead(DatasetCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
