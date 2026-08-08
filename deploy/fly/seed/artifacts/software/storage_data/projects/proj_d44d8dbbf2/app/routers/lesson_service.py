"""Router for lesson_service. Thin by design: logic lives in the service."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import schemas
from app.db import get_session
from app.services import lesson_service as service

router = APIRouter(tags=["lesson_service"])


@router.get("/lessons/{item_id}", response_model=schemas.LessonRead)
def get_lesson_846(item_id: int, session: Annotated[Session, Depends(get_session)]):
    """Get a lesson by ID"""
    obj = service.get_lesson(session, item_id)
    if obj is None:
        raise HTTPException(404, "Lesson not found")
    return obj


@router.post("/lessons", response_model=schemas.LessonRead, status_code=201)
def create_lesson_120(payload: schemas.LessonCreate, session: Annotated[Session, Depends(get_session)]):
    """Create a new lesson"""
    return service.create_lesson(session, payload.model_dump())


@router.get("/quizs", response_model=list[schemas.QuizRead])
def list_quiz_717(session: Annotated[Session, Depends(get_session)]):
    """List Quiz records"""
    return service.list_quizs(session)


@router.post("/quizs", response_model=schemas.QuizRead, status_code=201)
def create_quiz_759(payload: schemas.QuizCreate, session: Annotated[Session, Depends(get_session)]):
    """Create a Quiz"""
    return service.create_quiz(session, payload.model_dump())


@router.get("/quizs/{item_id}", response_model=schemas.QuizRead)
def get_quiz_532(item_id: int, session: Annotated[Session, Depends(get_session)]):
    """Fetch one Quiz"""
    obj = service.get_quiz(session, item_id)
    if obj is None:
        raise HTTPException(404, "Quiz not found")
    return obj


@router.delete("/quizs/{item_id}", status_code=204)
def delete_quiz_766(item_id: int, session: Annotated[Session, Depends(get_session)]):
    """Delete a Quiz"""
    if not service.delete_quiz(session, item_id):
        raise HTTPException(404, "Quiz not found")
