"""SQLAlchemy models — one class per domain entity."""

from datetime import datetime  # noqa: F401

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text  # noqa: F401
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Opportunity1(Base):
    __tablename__ = "opportunity1s"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    accepted: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    accepted_because: Mapped[str | None] = mapped_column(String(255), nullable=True)
    confidence: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    model_invoked: Mapped[str | None] = mapped_column(String(255), nullable=True)
    retrieved_context: Mapped[str | None] = mapped_column(String(255), nullable=True)
    type: Mapped[str | None] = mapped_column(String(255), nullable=True)

class Opportunity3(Base):
    __tablename__ = "opportunity3s"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    accepted: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    accepted_because: Mapped[str | None] = mapped_column(String(255), nullable=True)
    confidence: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    model_invoked: Mapped[str | None] = mapped_column(String(255), nullable=True)
    retrieved_context: Mapped[str | None] = mapped_column(String(255), nullable=True)
    type: Mapped[str | None] = mapped_column(String(255), nullable=True)

class Opportunity0(Base):
    __tablename__ = "opportunity0s"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    accepted: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    accepted_because: Mapped[str | None] = mapped_column(String(255), nullable=True)
    confidence: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    model_invoked: Mapped[str | None] = mapped_column(String(255), nullable=True)
    retrieved_context: Mapped[str | None] = mapped_column(String(255), nullable=True)
    type: Mapped[str | None] = mapped_column(String(255), nullable=True)

class Opportunity2(Base):
    __tablename__ = "opportunity2s"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    accepted: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    accepted_because: Mapped[str | None] = mapped_column(String(255), nullable=True)
    confidence: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    model_invoked: Mapped[str | None] = mapped_column(String(255), nullable=True)
    retrieved_context: Mapped[str | None] = mapped_column(String(255), nullable=True)
    type: Mapped[str | None] = mapped_column(String(255), nullable=True)

class Opportunity(Base):
    __tablename__ = "opportunitys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    accepted: Mapped[bool] = mapped_column(Boolean)
    accepted_because: Mapped[str] = mapped_column(String(255))
    confidence: Mapped[str] = mapped_column(String(255))
    created_by: Mapped[str] = mapped_column(String(255))
    model_invoked: Mapped[str] = mapped_column(String(255))
    retrieved_context: Mapped[str] = mapped_column(String(255))
    type: Mapped[str] = mapped_column(String(255))
