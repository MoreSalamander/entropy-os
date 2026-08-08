"""Router for curriculum_service. Thin by design: logic lives in the service."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import schemas
from app.db import get_session
from app.services import curriculum_service as service

router = APIRouter(tags=["curriculum_service"])


@router.get("/lessons/{item_id}", response_model=schemas.LessonRead)
def get_lesson_586(item_id: int, session: Annotated[Session, Depends(get_session)]):
    """"""
    obj = service.get_lesson(session, item_id)
    if obj is None:
        raise HTTPException(404, "Lesson not found")
    return obj
