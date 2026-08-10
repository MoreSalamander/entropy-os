"""Router for curriculum_service. Thin by design: logic lives in the service."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import schemas
from app.db import get_session
from app.services import curriculum_service as service

router = APIRouter(tags=["curriculum_service"])


@router.get("/concepts", response_model=list[schemas.ConceptRead])
def list_concept_622(session: Annotated[Session, Depends(get_session)]):
    """List Concept records"""
    return service.list_concepts(session)


@router.post("/concepts", response_model=schemas.ConceptRead, status_code=201)
def create_concept_41(payload: schemas.ConceptCreate, session: Annotated[Session, Depends(get_session)]):
    """Create a Concept"""
    return service.create_concept(session, payload.model_dump())


@router.get("/concepts/{item_id}", response_model=schemas.ConceptRead)
def get_concept_386(item_id: int, session: Annotated[Session, Depends(get_session)]):
    """Fetch one Concept"""
    obj = service.get_concept(session, item_id)
    if obj is None:
        raise HTTPException(404, "Concept not found")
    return obj


@router.delete("/concepts/{item_id}", status_code=204)
def delete_concept_715(item_id: int, session: Annotated[Session, Depends(get_session)]):
    """Delete a Concept"""
    if not service.delete_concept(session, item_id):
        raise HTTPException(404, "Concept not found")


@router.get("/users", response_model=list[schemas.UserRead])
def list_user_57(session: Annotated[Session, Depends(get_session)]):
    """List User records"""
    return service.list_users(session)


@router.post("/users", response_model=schemas.UserRead, status_code=201)
def create_user_803(payload: schemas.UserCreate, session: Annotated[Session, Depends(get_session)]):
    """Create a User"""
    return service.create_user(session, payload.model_dump())


@router.get("/users/{item_id}", response_model=schemas.UserRead)
def get_user_15(item_id: int, session: Annotated[Session, Depends(get_session)]):
    """Fetch one User"""
    obj = service.get_user(session, item_id)
    if obj is None:
        raise HTTPException(404, "User not found")
    return obj


@router.delete("/users/{item_id}", status_code=204)
def delete_user_276(item_id: int, session: Annotated[Session, Depends(get_session)]):
    """Delete a User"""
    if not service.delete_user(session, item_id):
        raise HTTPException(404, "User not found")


@router.get("/quiz_results", response_model=list[schemas.QuizResultRead])
def list_quiz_result_824(session: Annotated[Session, Depends(get_session)]):
    """List QuizResult records"""
    return service.list_quiz_results(session)


@router.post("/quiz_results", response_model=schemas.QuizResultRead, status_code=201)
def create_quiz_result_934(payload: schemas.QuizResultCreate, session: Annotated[Session, Depends(get_session)]):
    """Create a QuizResult"""
    return service.create_quiz_result(session, payload.model_dump())


@router.get("/quiz_results/{item_id}", response_model=schemas.QuizResultRead)
def get_quiz_result_221(item_id: int, session: Annotated[Session, Depends(get_session)]):
    """Fetch one QuizResult"""
    obj = service.get_quiz_result(session, item_id)
    if obj is None:
        raise HTTPException(404, "QuizResult not found")
    return obj


@router.delete("/quiz_results/{item_id}", status_code=204)
def delete_quiz_result_190(item_id: int, session: Annotated[Session, Depends(get_session)]):
    """Delete a QuizResult"""
    if not service.delete_quiz_result(session, item_id):
        raise HTTPException(404, "QuizResult not found")
