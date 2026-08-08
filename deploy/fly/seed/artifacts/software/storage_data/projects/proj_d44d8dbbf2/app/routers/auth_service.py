"""Router for auth_service. Thin by design: logic lives in the service."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import schemas
from app.db import get_session
from app.services import auth_service as service

router = APIRouter(tags=["auth_service"])


@router.get("/users", response_model=list[schemas.UserRead])
def list_user_308(session: Annotated[Session, Depends(get_session)]):
    """List User records"""
    return service.list_users(session)


@router.post("/users", response_model=schemas.UserRead, status_code=201)
def create_user_961(payload: schemas.UserCreate, session: Annotated[Session, Depends(get_session)]):
    """Create a User"""
    return service.create_user(session, payload.model_dump())


@router.get("/users/{item_id}", response_model=schemas.UserRead)
def get_user_469(item_id: int, session: Annotated[Session, Depends(get_session)]):
    """Fetch one User"""
    obj = service.get_user(session, item_id)
    if obj is None:
        raise HTTPException(404, "User not found")
    return obj


@router.delete("/users/{item_id}", status_code=204)
def delete_user_702(item_id: int, session: Annotated[Session, Depends(get_session)]):
    """Delete a User"""
    if not service.delete_user(session, item_id):
        raise HTTPException(404, "User not found")
