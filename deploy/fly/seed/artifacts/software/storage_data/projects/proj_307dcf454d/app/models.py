"""SQLAlchemy models — one class per domain entity."""

from datetime import datetime  # noqa: F401

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text  # noqa: F401
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(255))
    password_hash: Mapped[str] = mapped_column(String(255))
    email: Mapped[str] = mapped_column(String(255))

class LessonContent(Base):
    __tablename__ = "lesson_contents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text)
    multimedia_content: Mapped[str] = mapped_column(String(255))

class Quiz(Base):
    __tablename__ = "quizs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    concept_id: Mapped[int] = mapped_column(Integer)
    question: Mapped[str] = mapped_column(String(255))
    answer: Mapped[bool] = mapped_column(Boolean)

class UserProgress(Base):
    __tablename__ = "user_progresss"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer)
    concept_id: Mapped[int] = mapped_column(Integer)
    mastery_level: Mapped[float] = mapped_column(Float)
