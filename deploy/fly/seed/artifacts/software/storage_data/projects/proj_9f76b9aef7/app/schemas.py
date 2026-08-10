"""Pydantic schemas: every request validated, every response shaped."""

from datetime import datetime  # noqa: F401

from pydantic import BaseModel, ConfigDict


class CountryCodeCreate(BaseModel):
    code: str
    description: str


class CountryCodeRead(CountryCodeCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int

class PhoneNumberCreate(BaseModel):
    number: str
    country_code: str


class PhoneNumberRead(PhoneNumberCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
