"""Router for phone_formatter_service. Thin by design: logic lives in the service."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import schemas
from app.db import get_session
from app.services import phone_formatter_service as service

router = APIRouter(tags=["phone_formatter_service"])


@router.post("/format-phone-number")
def create_op_439():
    """Format a phone number (STUB — custom logic not yet implemented)"""
    return {"implemented": False,
            "endpoint": "POST /format-phone-number",
            "summary": "Format a phone number"}


@router.get("/phone_numbers", response_model=list[schemas.PhoneNumberRead])
def list_phone_number_333(session: Annotated[Session, Depends(get_session)]):
    """List PhoneNumber records"""
    return service.list_phone_numbers(session)


@router.post("/phone_numbers", response_model=schemas.PhoneNumberRead, status_code=201)
def create_phone_number_889(payload: schemas.PhoneNumberCreate, session: Annotated[Session, Depends(get_session)]):
    """Create a PhoneNumber"""
    return service.create_phone_number(session, payload.model_dump())


@router.get("/phone_numbers/{item_id}", response_model=schemas.PhoneNumberRead)
def get_phone_number_252(item_id: int, session: Annotated[Session, Depends(get_session)]):
    """Fetch one PhoneNumber"""
    obj = service.get_phone_number(session, item_id)
    if obj is None:
        raise HTTPException(404, "PhoneNumber not found")
    return obj


@router.delete("/phone_numbers/{item_id}", status_code=204)
def delete_phone_number_224(item_id: int, session: Annotated[Session, Depends(get_session)]):
    """Delete a PhoneNumber"""
    if not service.delete_phone_number(session, item_id):
        raise HTTPException(404, "PhoneNumber not found")
