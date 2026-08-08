"""Router for quiz_service. Thin by design: logic lives in the service."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import schemas
from app.db import get_session
from app.services import quiz_service as service

router = APIRouter(tags=["quiz_service"])


@router.post("/quizzes/{lesson_id}")
def create_op_469():
    """ (STUB — custom logic not yet implemented)"""
    return {"implemented": False,
            "endpoint": "POST /quizzes/{lesson_id}",
            "summary": ""}


@router.get("/user_progress", response_model=list[schemas.UserRead])
def list_user_534(session: Annotated[Session, Depends(get_session)]):
    """"""
    return service.list_users(session)


@router.get("/quiz_results", response_model=list[schemas.QuizResultRead])
def list_quiz_result_884(session: Annotated[Session, Depends(get_session)]):
    """List QuizResult records"""
    return service.list_quiz_results(session)


@router.post("/quiz_results", response_model=schemas.QuizResultRead, status_code=201)
def create_quiz_result_151(payload: schemas.QuizResultCreate, session: Annotated[Session, Depends(get_session)]):
    """Create a QuizResult"""
    return service.create_quiz_result(session, payload.model_dump())


@router.get("/quiz_results/{item_id}", response_model=schemas.QuizResultRead)
def get_quiz_result_413(item_id: int, session: Annotated[Session, Depends(get_session)]):
    """Fetch one QuizResult"""
    obj = service.get_quiz_result(session, item_id)
    if obj is None:
        raise HTTPException(404, "QuizResult not found")
    return obj


@router.delete("/quiz_results/{item_id}", status_code=204)
def delete_quiz_result_37(item_id: int, session: Annotated[Session, Depends(get_session)]):
    """Delete a QuizResult"""
    if not service.delete_quiz_result(session, item_id):
        raise HTTPException(404, "QuizResult not found")
