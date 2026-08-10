"""Service layer for gate_outcome_service: Handles gate outcome-related operations"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models


def list_gate_outcomes(session: Session) -> list[models.GateOutcome]:
    return list(session.scalars(select(models.GateOutcome)).all())


def get_gate_outcome(session: Session, item_id: int) -> models.GateOutcome | None:
    return session.get(models.GateOutcome, item_id)


def create_gate_outcome(session: Session, data: dict) -> models.GateOutcome:
    obj = models.GateOutcome(**data)
    session.add(obj)
    session.commit()
    session.refresh(obj)
    return obj


def delete_gate_outcome(session: Session, item_id: int) -> bool:
    obj = session.get(models.GateOutcome, item_id)
    if obj is None:
        return False
    session.delete(obj)
    session.commit()
    return True
