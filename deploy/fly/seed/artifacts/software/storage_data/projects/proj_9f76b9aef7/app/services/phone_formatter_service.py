"""Service layer for phone_formatter_service: Handles phone number formatting and validation"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models


def list_phone_numbers(session: Session) -> list[models.PhoneNumber]:
    return list(session.scalars(select(models.PhoneNumber)).all())


def get_phone_number(session: Session, item_id: int) -> models.PhoneNumber | None:
    return session.get(models.PhoneNumber, item_id)


def create_phone_number(session: Session, data: dict) -> models.PhoneNumber:
    obj = models.PhoneNumber(**data)
    session.add(obj)
    session.commit()
    session.refresh(obj)
    return obj


def delete_phone_number(session: Session, item_id: int) -> bool:
    obj = session.get(models.PhoneNumber, item_id)
    if obj is None:
        return False
    session.delete(obj)
    session.commit()
    return True
