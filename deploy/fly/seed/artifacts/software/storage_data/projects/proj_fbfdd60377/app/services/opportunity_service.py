"""Service layer for opportunity_service: Record and query gate outcomes of hunter runs"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models


def list_opportunitys(session: Session) -> list[models.Opportunity]:
    return list(session.scalars(select(models.Opportunity)).all())


def get_opportunity(session: Session, item_id: int) -> models.Opportunity | None:
    return session.get(models.Opportunity, item_id)


def create_opportunity(session: Session, data: dict) -> models.Opportunity:
    obj = models.Opportunity(**data)
    session.add(obj)
    session.commit()
    session.refresh(obj)
    return obj


def delete_opportunity(session: Session, item_id: int) -> bool:
    obj = session.get(models.Opportunity, item_id)
    if obj is None:
        return False
    session.delete(obj)
    session.commit()
    return True
