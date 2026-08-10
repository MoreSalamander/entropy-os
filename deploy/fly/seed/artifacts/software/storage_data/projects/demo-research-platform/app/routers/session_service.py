"""Router for session_service. Thin by design: logic lives in the service."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import schemas  # noqa: F401
from app.db import get_session
from app.services import session_service as service

router = APIRouter(tags=["session_service"])


@router.post("/sessions")
def create_op_252():
    """Create a new session (STUB — custom logic not yet implemented)"""
    return {"implemented": False,
            "endpoint": "POST /sessions",
            "summary": "Create a new session"}
