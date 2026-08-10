"""Service layer for string_reverser_service: Reverse input string with correct character order"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models


def list_string_reversal_requests(session: Session) -> list[models.StringReversalRequest]:
    return list(session.scalars(select(models.StringReversalRequest)).all())


def get_string_reversal_request(session: Session, item_id: int) -> models.StringReversalRequest | None:
    return session.get(models.StringReversalRequest, item_id)


def create_string_reversal_request(session: Session, data: dict) -> models.StringReversalRequest:
    obj = models.StringReversalRequest(**data)
    session.add(obj)
    session.commit()
    session.refresh(obj)
    return obj


def delete_string_reversal_request(session: Session, item_id: int) -> bool:
    obj = session.get(models.StringReversalRequest, item_id)
    if obj is None:
        return False
    session.delete(obj)
    session.commit()
    return True


def list_string_reversal_responses(session: Session) -> list[models.StringReversalResponse]:
    return list(session.scalars(select(models.StringReversalResponse)).all())


def get_string_reversal_response(session: Session, item_id: int) -> models.StringReversalResponse | None:
    return session.get(models.StringReversalResponse, item_id)


def create_string_reversal_response(session: Session, data: dict) -> models.StringReversalResponse:
    obj = models.StringReversalResponse(**data)
    session.add(obj)
    session.commit()
    session.refresh(obj)
    return obj


def delete_string_reversal_response(session: Session, item_id: int) -> bool:
    obj = session.get(models.StringReversalResponse, item_id)
    if obj is None:
        return False
    session.delete(obj)
    session.commit()
    return True
