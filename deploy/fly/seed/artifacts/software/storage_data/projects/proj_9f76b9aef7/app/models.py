"""SQLAlchemy models — one class per domain entity."""

from datetime import datetime  # noqa: F401

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text  # noqa: F401
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class CountryCode(Base):
    __tablename__ = "country_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text)

class PhoneNumber(Base):
    __tablename__ = "phone_numbers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    number: Mapped[str] = mapped_column(String(255))
    country_code: Mapped[str] = mapped_column(String(255))
