"""Router for gate_outcome_service. Thin by design: logic lives in the service."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import schemas
from app.db import get_session
from app.services import gate_outcome_service as service

router = APIRouter(tags=["gate_outcome_service"])


@router.post("/gate-outcomes", response_model=schemas.HunterRunOutcomeRead, status_code=201)
def create_hunter_run_outcome_252(payload: schemas.HunterRunOutcomeCreate, session: Annotated[Session, Depends(get_session)]):
    """Create a new gate outcome record"""
    return service.create_hunter_run_outcome(session, payload.model_dump())


@router.get("/gate-outcomes")
def list_op_989():
    """Query recorded gate outcomes by filters (STUB — custom logic not yet implemented)"""
    return {"implemented": False,
            "endpoint": "GET /gate-outcomes",
            "summary": "Query recorded gate outcomes by filters"}


@router.get("/opportunitys", response_model=list[schemas.OpportunityRead])
def list_opportunity_350(session: Annotated[Session, Depends(get_session)]):
    """List Opportunity records"""
    return service.list_opportunitys(session)


@router.post("/opportunitys", response_model=schemas.OpportunityRead, status_code=201)
def create_opportunity_19(payload: schemas.OpportunityCreate, session: Annotated[Session, Depends(get_session)]):
    """Create a Opportunity"""
    return service.create_opportunity(session, payload.model_dump())


@router.get("/opportunitys/{item_id}", response_model=schemas.OpportunityRead)
def get_opportunity_987(item_id: int, session: Annotated[Session, Depends(get_session)]):
    """Fetch one Opportunity"""
    obj = service.get_opportunity(session, item_id)
    if obj is None:
        raise HTTPException(404, "Opportunity not found")
    return obj


@router.delete("/opportunitys/{item_id}", status_code=204)
def delete_opportunity_635(item_id: int, session: Annotated[Session, Depends(get_session)]):
    """Delete a Opportunity"""
    if not service.delete_opportunity(session, item_id):
        raise HTTPException(404, "Opportunity not found")
