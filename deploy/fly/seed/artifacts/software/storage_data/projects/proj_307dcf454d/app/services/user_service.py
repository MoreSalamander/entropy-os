"""Service layer for user_service: manages user accounts and progress tracking"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models


def list_users(session: Session) -> list[models.User]:
    return list(session.scalars(select(models.User)).all())


def get_user(session: Session, item_id: int) -> models.User | None:
    return session.get(models.User, item_id)


def create_user(session: Session, data: dict) -> models.User:
    obj = models.User(**data)
    session.add(obj)
    session.commit()
    session.refresh(obj)
    return obj


def delete_user(session: Session, item_id: int) -> bool:
    obj = session.get(models.User, item_id)
    if obj is None:
        return False
    session.delete(obj)
    session.commit()
    return True


def list_user_progresss(session: Session) -> list[models.UserProgress]:
    return list(session.scalars(select(models.UserProgress)).all())


def get_user_progress(session: Session, item_id: int) -> models.UserProgress | None:
    return session.get(models.UserProgress, item_id)


def create_user_progress(session: Session, data: dict) -> models.UserProgress:
    obj = models.UserProgress(**data)
    session.add(obj)
    session.commit()
    session.refresh(obj)
    return obj


def delete_user_progress(session: Session, item_id: int) -> bool:
    obj = session.get(models.UserProgress, item_id)
    if obj is None:
        return False
    session.delete(obj)
    session.commit()
    return True
