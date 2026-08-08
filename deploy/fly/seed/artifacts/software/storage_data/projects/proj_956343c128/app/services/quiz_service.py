"""Service layer for quiz_service: Manages graded quizzes and user progress."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models


def list_quiz_results(session: Session) -> list[models.QuizResult]:
    return list(session.scalars(select(models.QuizResult)).all())


def get_quiz_result(session: Session, item_id: int) -> models.QuizResult | None:
    return session.get(models.QuizResult, item_id)


def create_quiz_result(session: Session, data: dict) -> models.QuizResult:
    obj = models.QuizResult(**data)
    session.add(obj)
    session.commit()
    session.refresh(obj)
    return obj


def delete_quiz_result(session: Session, item_id: int) -> bool:
    obj = session.get(models.QuizResult, item_id)
    if obj is None:
        return False
    session.delete(obj)
    session.commit()
    return True


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
