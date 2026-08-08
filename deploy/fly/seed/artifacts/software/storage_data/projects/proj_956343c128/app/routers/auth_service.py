"""Router for auth_service. Thin by design: logic lives in the service."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import schemas
from app.db import get_session
from app.services import auth_service as service

router = APIRouter(tags=["auth_service"])


@router.post("/login")
def create_op_18():
    """ (STUB — custom logic not yet implemented)"""
    return {"implemented": False,
            "endpoint": "POST /login",
            "summary": ""}


@router.get("/user_info", response_model=list[schemas.UserRead])
def list_user_236(session: Annotated[Session, Depends(get_session)]):
    """"""
    return service.list_users(session)
