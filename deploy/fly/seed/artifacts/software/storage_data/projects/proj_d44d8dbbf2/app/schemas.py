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

class LessonCreate(BaseModel):
    title: str
    description: str
    code_snippet: str


class LessonRead(LessonCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int

class QuizCreate(BaseModel):
    title: str
    description: str
    questions: str


class QuizRead(QuizCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
