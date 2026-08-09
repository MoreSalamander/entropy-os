"""Router for opportunity_service. Thin by design: logic lives in the service."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import schemas
from app.db import get_session
from app.services import opportunity_service as service

router = APIRouter(tags=["opportunity_service"])


@router.get("/opportunities")
def list_op_69():
    """List all opportunities (STUB — custom logic not yet implemented)"""
    return {"implemented": False,
            "endpoint": "GET /opportunities",
            "summary": "List all opportunities"}


@router.post("/opportunities")
def create_op_532():
    """Create a new opportunity (STUB — custom logic not yet implemented)"""
    return {"implemented": False,
            "endpoint": "POST /opportunities",
            "summary": "Create a new opportunity"}


@router.get("/opportunities/{item_id}", response_model=schemas.OpportunityRead)
def get_opportunity_861(item_id: int, session: Annotated[Session, Depends(get_session)]):
    """Get an opportunity by ID"""
    obj = service.get_opportunity(session, item_id)
    if obj is None:
        raise HTTPException(404, "Opportunity not found")
    return obj


@router.put("/opportunities/{item_id}", response_model=schemas.OpportunityRead)
def update_opportunity_432(item_id: int, payload: schemas.OpportunityCreate, session: Annotated[Session, Depends(get_session)]):
    """Update an opportunity"""
    obj = service.get_opportunity(session, item_id)
    if obj is None:
        raise HTTPException(404, "Opportunity not found")
    for key, value in payload.model_dump().items():
        setattr(obj, key, value)
    session.commit()
    session.refresh(obj)
    return obj
