"""SQLAlchemy models — one class per domain entity."""

from datetime import datetime  # noqa: F401

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text  # noqa: F401
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class HunterRunOutcome(Base):
    __tablename__ = "hunter_run_outcomes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    hunter_run_id: Mapped[str] = mapped_column(String(255))
    gate_outcome: Mapped[str] = mapped_column(String(255))
    opportunity_type: Mapped[str] = mapped_column(String(255))
    model_invoked: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime)

class Opportunity(Base):
    __tablename__ = "opportunitys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    hunter_run_id: Mapped[str] = mapped_column(String(255))
    opportunity_type: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime)
