"""Router for access_control_service. Thin by design: logic lives in the service."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import schemas  # noqa: F401
from app.db import get_session
from app.services import access_control_service as service

router = APIRouter(tags=["access_control_service"])


@router.post("/users/{id}/roles")
def create_op_69():
    """Assign a role to a user (STUB — custom logic not yet implemented)"""
    return {"implemented": False,
            "endpoint": "POST /users/{id}/roles",
            "summary": "Assign a role to a user"}
