"""Router for gate_outcome_service. Thin by design: logic lives in the service."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import schemas
from app.db import get_session
from app.services import gate_outcome_service as service

router = APIRouter(tags=["gate_outcome_service"])


@router.get("/gate-outcomes/{item_id}", response_model=schemas.GateOutcomeRead)
def get_gate_outcome_641(item_id: int, session: Annotated[Session, Depends(get_session)]):
    """Get gate outcome by ID"""
    obj = service.get_gate_outcome(session, item_id)
    if obj is None:
        raise HTTPException(404, "GateOutcome not found")
    return obj


@router.get("/gate-outcomes")
def list_op_989():
    """Get all gate outcomes (STUB — custom logic not yet implemented)"""
    return {"implemented": False,
            "endpoint": "GET /gate-outcomes",
            "summary": "Get all gate outcomes"}
