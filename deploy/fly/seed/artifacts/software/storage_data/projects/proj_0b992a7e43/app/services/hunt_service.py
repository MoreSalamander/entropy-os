"""Service layer for hunt_service: Handles hunt-related operations"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models


def list_hunter_runs(session: Session) -> list[models.HunterRun]:
    return list(session.scalars(select(models.HunterRun)).all())


def get_hunter_run(session: Session, item_id: int) -> models.HunterRun | None:
    return session.get(models.HunterRun, item_id)


def create_hunter_run(session: Session, data: dict) -> models.HunterRun:
    obj = models.HunterRun(**data)
    session.add(obj)
    session.commit()
    session.refresh(obj)
    return obj


def delete_hunter_run(session: Session, item_id: int) -> bool:
    obj = session.get(models.HunterRun, item_id)
    if obj is None:
        return False
    session.delete(obj)
    session.commit()
    return True
