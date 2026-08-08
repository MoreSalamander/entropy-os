"""Service layer for curriculum_service: Provides access to the revised curriculum."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models


def list_lessons(session: Session) -> list[models.Lesson]:
    return list(session.scalars(select(models.Lesson)).all())


def get_lesson(session: Session, item_id: int) -> models.Lesson | None:
    return session.get(models.Lesson, item_id)


def create_lesson(session: Session, data: dict) -> models.Lesson:
    obj = models.Lesson(**data)
    session.add(obj)
    session.commit()
    session.refresh(obj)
    return obj


def delete_lesson(session: Session, item_id: int) -> bool:
    obj = session.get(models.Lesson, item_id)
    if obj is None:
        return False
    session.delete(obj)
    session.commit()
    return True
