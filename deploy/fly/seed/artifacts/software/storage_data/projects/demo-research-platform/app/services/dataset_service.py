"""Service layer for dataset_service: Store and manage user-uploaded datasets"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models


def list_datasets(session: Session) -> list[models.Dataset]:
    return list(session.scalars(select(models.Dataset)).all())


def get_dataset(session: Session, item_id: int) -> models.Dataset | None:
    return session.get(models.Dataset, item_id)


def create_dataset(session: Session, data: dict) -> models.Dataset:
    obj = models.Dataset(**data)
    session.add(obj)
    session.commit()
    session.refresh(obj)
    return obj


def delete_dataset(session: Session, item_id: int) -> bool:
    obj = session.get(models.Dataset, item_id)
    if obj is None:
        return False
    session.delete(obj)
    session.commit()
    return True
