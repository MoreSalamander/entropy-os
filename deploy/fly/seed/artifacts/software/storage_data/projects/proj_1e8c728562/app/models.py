"""SQLAlchemy models — one class per domain entity."""

from datetime import datetime  # noqa: F401

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text  # noqa: F401
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class StringReversalRequest(Base):
    __tablename__ = "string_reversal_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    input_string: Mapped[str] = mapped_column(String(255))

class StringReversalResponse(Base):
    __tablename__ = "string_reversal_responses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    reversed_string: Mapped[str] = mapped_column(String(255))
