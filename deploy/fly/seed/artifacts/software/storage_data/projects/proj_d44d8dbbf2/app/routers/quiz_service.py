"""Router for quiz_service. Thin by design: logic lives in the service."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import schemas
from app.db import get_session
from app.services import quiz_service as service

router = APIRouter(tags=["quiz_service"])


@router.get("/quizzes/{item_id}", response_model=schemas.QuizRead)
def get_quiz_409(item_id: int, session: Annotated[Session, Depends(get_session)]):
    """Get a quiz by ID"""
    obj = service.get_quiz(session, item_id)
    if obj is None:
        raise HTTPException(404, "Quiz not found")
    return obj


@router.post("/quizzes", response_model=schemas.QuizRead, status_code=201)
def create_quiz_928(payload: schemas.QuizCreate, session: Annotated[Session, Depends(get_session)]):
    """Create a new quiz"""
    return service.create_quiz(session, payload.model_dump())
