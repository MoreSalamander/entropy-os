"""Service layer for lesson_service: manages lesson content and quizzes"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models


def list_lesson_contents(session: Session) -> list[models.LessonContent]:
    return list(session.scalars(select(models.LessonContent)).all())


def get_lesson_content(session: Session, item_id: int) -> models.LessonContent | None:
    return session.get(models.LessonContent, item_id)


def create_lesson_content(session: Session, data: dict) -> models.LessonContent:
    obj = models.LessonContent(**data)
    session.add(obj)
    session.commit()
    session.refresh(obj)
    return obj


def delete_lesson_content(session: Session, item_id: int) -> bool:
    obj = session.get(models.LessonContent, item_id)
    if obj is None:
        return False
    session.delete(obj)
    session.commit()
    return True


def list_quizs(session: Session) -> list[models.Quiz]:
    return list(session.scalars(select(models.Quiz)).all())


def get_quiz(session: Session, item_id: int) -> models.Quiz | None:
    return session.get(models.Quiz, item_id)


def create_quiz(session: Session, data: dict) -> models.Quiz:
    obj = models.Quiz(**data)
    session.add(obj)
    session.commit()
    session.refresh(obj)
    return obj


def delete_quiz(session: Session, item_id: int) -> bool:
    obj = session.get(models.Quiz, item_id)
    if obj is None:
        return False
    session.delete(obj)
    session.commit()
    return True
