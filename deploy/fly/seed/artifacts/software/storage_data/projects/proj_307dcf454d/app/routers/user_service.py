"""Router for user_service. Thin by design: logic lives in the service."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import schemas
from app.db import get_session
from app.services import user_service as service

router = APIRouter(tags=["user_service"])


@router.get("/users", response_model=list[schemas.UserRead])
def list_user_12(session: Annotated[Session, Depends(get_session)]):
    """List User records"""
    return service.list_users(session)


@router.post("/users", response_model=schemas.UserRead, status_code=201)
def create_user_956(payload: schemas.UserCreate, session: Annotated[Session, Depends(get_session)]):
    """Create a User"""
    return service.create_user(session, payload.model_dump())


@router.get("/users/{item_id}", response_model=schemas.UserRead)
def get_user_261(item_id: int, session: Annotated[Session, Depends(get_session)]):
    """Fetch one User"""
    obj = service.get_user(session, item_id)
    if obj is None:
        raise HTTPException(404, "User not found")
    return obj


@router.delete("/users/{item_id}", status_code=204)
def delete_user_633(item_id: int, session: Annotated[Session, Depends(get_session)]):
    """Delete a User"""
    if not service.delete_user(session, item_id):
        raise HTTPException(404, "User not found")


@router.get("/user_progresss", response_model=list[schemas.UserProgressRead])
def list_user_progress_388(session: Annotated[Session, Depends(get_session)]):
    """List UserProgress records"""
    return service.list_user_progresss(session)


@router.post("/user_progresss", response_model=schemas.UserProgressRead, status_code=201)
def create_user_progress_619(payload: schemas.UserProgressCreate, session: Annotated[Session, Depends(get_session)]):
    """Create a UserProgress"""
    return service.create_user_progress(session, payload.model_dump())


@router.get("/user_progresss/{item_id}", response_model=schemas.UserProgressRead)
def get_user_progress_472(item_id: int, session: Annotated[Session, Depends(get_session)]):
    """Fetch one UserProgress"""
    obj = service.get_user_progress(session, item_id)
    if obj is None:
        raise HTTPException(404, "UserProgress not found")
    return obj


@router.delete("/user_progresss/{item_id}", status_code=204)
def delete_user_progress_924(item_id: int, session: Annotated[Session, Depends(get_session)]):
    """Delete a UserProgress"""
    if not service.delete_user_progress(session, item_id):
        raise HTTPException(404, "UserProgress not found")
