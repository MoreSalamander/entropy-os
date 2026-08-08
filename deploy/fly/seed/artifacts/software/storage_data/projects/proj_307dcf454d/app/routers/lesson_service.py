"""Router for lesson_service. Thin by design: logic lives in the service."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import schemas
from app.db import get_session
from app.services import lesson_service as service

router = APIRouter(tags=["lesson_service"])


@router.get("/lesson_contents", response_model=list[schemas.LessonContentRead])
def list_lesson_content_189(session: Annotated[Session, Depends(get_session)]):
    """List LessonContent records"""
    return service.list_lesson_contents(session)


@router.post("/lesson_contents", response_model=schemas.LessonContentRead, status_code=201)
def create_lesson_content_871(payload: schemas.LessonContentCreate, session: Annotated[Session, Depends(get_session)]):
    """Create a LessonContent"""
    return service.create_lesson_content(session, payload.model_dump())


@router.get("/lesson_contents/{item_id}", response_model=schemas.LessonContentRead)
def get_lesson_content_197(item_id: int, session: Annotated[Session, Depends(get_session)]):
    """Fetch one LessonContent"""
    obj = service.get_lesson_content(session, item_id)
    if obj is None:
        raise HTTPException(404, "LessonContent not found")
    return obj


@router.delete("/lesson_contents/{item_id}", status_code=204)
def delete_lesson_content_368(item_id: int, session: Annotated[Session, Depends(get_session)]):
    """Delete a LessonContent"""
    if not service.delete_lesson_content(session, item_id):
        raise HTTPException(404, "LessonContent not found")


@router.get("/quizs", response_model=list[schemas.QuizRead])
def list_quiz_972(session: Annotated[Session, Depends(get_session)]):
    """List Quiz records"""
    return service.list_quizs(session)


@router.post("/quizs", response_model=schemas.QuizRead, status_code=201)
def create_quiz_614(payload: schemas.QuizCreate, session: Annotated[Session, Depends(get_session)]):
    """Create a Quiz"""
    return service.create_quiz(session, payload.model_dump())


@router.get("/quizs/{item_id}", response_model=schemas.QuizRead)
def get_quiz_276(item_id: int, session: Annotated[Session, Depends(get_session)]):
    """Fetch one Quiz"""
    obj = service.get_quiz(session, item_id)
    if obj is None:
        raise HTTPException(404, "Quiz not found")
    return obj


@router.delete("/quizs/{item_id}", status_code=204)
def delete_quiz_934(item_id: int, session: Annotated[Session, Depends(get_session)]):
    """Delete a Quiz"""
    if not service.delete_quiz(session, item_id):
        raise HTTPException(404, "Quiz not found")
