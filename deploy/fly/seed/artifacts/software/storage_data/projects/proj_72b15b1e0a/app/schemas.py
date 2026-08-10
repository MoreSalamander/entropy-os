"""Pydantic schemas: every request validated, every response shaped."""

from datetime import datetime  # noqa: F401

from pydantic import BaseModel, ConfigDict


class UserCreate(BaseModel):
    username: str
    email: str
    password_hash: str


class UserRead(UserCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int

class ConceptCreate(BaseModel):
    title: str
    description: str


class ConceptRead(ConceptCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int

class QuizResultCreate(BaseModel):
    concept_id: int
    user_id: int
    score: float


class QuizResultRead(QuizResultCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
