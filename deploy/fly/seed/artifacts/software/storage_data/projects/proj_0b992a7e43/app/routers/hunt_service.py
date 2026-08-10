"""Router for hunt_service. Thin by design: logic lives in the service."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import schemas
from app.db import get_session
from app.services import hunt_service as service

router = APIRouter(tags=["hunt_service"])


@router.get("/hunter_runs", response_model=list[schemas.HunterRunRead])
def list_hunter_run_347(session: Annotated[Session, Depends(get_session)]):
    """List HunterRun records"""
    return service.list_hunter_runs(session)


@router.post("/hunter_runs", response_model=schemas.HunterRunRead, status_code=201)
def create_hunter_run_32(payload: schemas.HunterRunCreate, session: Annotated[Session, Depends(get_session)]):
    """Create a HunterRun"""
    return service.create_hunter_run(session, payload.model_dump())


@router.get("/hunter_runs/{item_id}", response_model=schemas.HunterRunRead)
def get_hunter_run_836(item_id: int, session: Annotated[Session, Depends(get_session)]):
    """Fetch one HunterRun"""
    obj = service.get_hunter_run(session, item_id)
    if obj is None:
        raise HTTPException(404, "HunterRun not found")
    return obj


@router.delete("/hunter_runs/{item_id}", status_code=204)
def delete_hunter_run_210(item_id: int, session: Annotated[Session, Depends(get_session)]):
    """Delete a HunterRun"""
    if not service.delete_hunter_run(session, item_id):
        raise HTTPException(404, "HunterRun not found")
