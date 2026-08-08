"""Pydantic schemas: every request validated, every response shaped."""

from datetime import datetime  # noqa: F401

from pydantic import BaseModel, ConfigDict


class UserCreate(BaseModel):
    username: str
    email: str


class UserRead(UserCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int

class LessonCreate(BaseModel):
    title: str
    content: str
    updated_at: datetime


class LessonRead(LessonCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int

class QuizResultCreate(BaseModel):
    user_id: int
    lesson_id: int
    score: float


class QuizResultRead(QuizResultCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
