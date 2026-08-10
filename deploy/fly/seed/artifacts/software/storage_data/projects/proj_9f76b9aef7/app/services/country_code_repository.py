"""Service layer for country_code_repository: Stores and retrieves country codes for formatting"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models


def list_country_codes(session: Session) -> list[models.CountryCode]:
    return list(session.scalars(select(models.CountryCode)).all())


def get_country_code(session: Session, item_id: int) -> models.CountryCode | None:
    return session.get(models.CountryCode, item_id)


def create_country_code(session: Session, data: dict) -> models.CountryCode:
    obj = models.CountryCode(**data)
    session.add(obj)
    session.commit()
    session.refresh(obj)
    return obj


def delete_country_code(session: Session, item_id: int) -> bool:
    obj = session.get(models.CountryCode, item_id)
    if obj is None:
        return False
    session.delete(obj)
    session.commit()
    return True
