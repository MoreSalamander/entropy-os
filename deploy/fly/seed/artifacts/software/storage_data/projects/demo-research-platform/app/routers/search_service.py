"""Router for search_service. Thin by design: logic lives in the service."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import schemas  # noqa: F401
from app.db import get_session
from app.services import search_service as service

router = APIRouter(tags=["search_service"])


@router.get("/users", response_model=list[schemas.UserRead])
def list_user_525(session: Session = Depends(get_session)):
    """List User records"""
    return service.list_users(session)


@router.post("/users", response_model=schemas.UserRead, status_code=201)
def create_user_42(payload: schemas.UserCreate, session: Session = Depends(get_session)):
    """Create a User"""
    return service.create_user(session, payload.model_dump())


@router.get("/users/{item_id}", response_model=schemas.UserRead)
def get_user_318(item_id: int, session: Session = Depends(get_session)):
    """Fetch one User"""
    obj = service.get_user(session, item_id)
    if obj is None:
        raise HTTPException(404, "User not found")
    return obj


@router.delete("/users/{item_id}", status_code=204)
def delete_user_381(item_id: int, session: Session = Depends(get_session)):
    """Delete a User"""
    if not service.delete_user(session, item_id):
        raise HTTPException(404, "User not found")
