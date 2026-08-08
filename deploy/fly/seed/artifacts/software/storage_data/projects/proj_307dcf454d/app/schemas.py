"""Pydantic schemas: every request validated, every response shaped."""

from datetime import datetime  # noqa: F401

from pydantic import BaseModel, ConfigDict


class UserCreate(BaseModel):
    username: str
    password_hash: str
    email: str


class UserRead(UserCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int

class LessonContentCreate(BaseModel):
    title: str
    description: str
    multimedia_content: str


class LessonContentRead(LessonContentCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int

class QuizCreate(BaseModel):
    concept_id: int
    question: str
    answer: bool


class QuizRead(QuizCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int

class UserProgressCreate(BaseModel):
    user_id: int
    concept_id: int
    mastery_level: float


class UserProgressRead(UserProgressCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
