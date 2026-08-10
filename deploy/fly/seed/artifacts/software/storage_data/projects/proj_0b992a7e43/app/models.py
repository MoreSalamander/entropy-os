"""SQLAlchemy models — one class per domain entity."""

from datetime import datetime  # noqa: F401

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text  # noqa: F401
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class HunterRun(Base):
    __tablename__ = "hunter_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    hunter_id: Mapped[str] = mapped_column(String(255))
    location: Mapped[str] = mapped_column(String(255))
    timestamp: Mapped[datetime] = mapped_column(DateTime)

class GateOutcome(Base):
    __tablename__ = "gate_outcomes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    hunter_run_id: Mapped[int] = mapped_column(Integer)
    gate_outcome: Mapped[str] = mapped_column(String(255))
