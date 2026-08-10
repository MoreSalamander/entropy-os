"""Router for dataset_service. Thin by design: logic lives in the service."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import schemas  # noqa: F401
from app.db import get_session
from app.services import dataset_service as service

router = APIRouter(tags=["dataset_service"])


@router.post("/datasets", response_model=schemas.DatasetRead, status_code=201)
def create_dataset_376(payload: schemas.DatasetCreate, session: Session = Depends(get_session)):
    """Create a new dataset"""
    return service.create_dataset(session, payload.model_dump())


@router.get("/datasets/{id}", response_model=schemas.DatasetRead)
def get_dataset_370(item_id: int, session: Session = Depends(get_session)):
    """Get a dataset by ID"""
    obj = service.get_dataset(session, item_id)
    if obj is None:
        raise HTTPException(404, "Dataset not found")
    return obj
