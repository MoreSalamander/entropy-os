"""Router for string_reverser_service. Thin by design: logic lives in the service."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import schemas
from app.db import get_session
from app.services import string_reverser_service as service

router = APIRouter(tags=["string_reverser_service"])


@router.post("/reverse-string")
def create_op_216():
    """Reverse input string with correct character order (STUB — custom logic not yet implemented)"""
    return {"implemented": False,
            "endpoint": "POST /reverse-string",
            "summary": "Reverse input string with correct character order"}


@router.get("/string_reversal_requests", response_model=list[schemas.StringReversalRequestRead])
def list_string_reversal_request_275(session: Annotated[Session, Depends(get_session)]):
    """List StringReversalRequest records"""
    return service.list_string_reversal_requests(session)


@router.post("/string_reversal_requests", response_model=schemas.StringReversalRequestRead, status_code=201)
def create_string_reversal_request_356(payload: schemas.StringReversalRequestCreate, session: Annotated[Session, Depends(get_session)]):
    """Create a StringReversalRequest"""
    return service.create_string_reversal_request(session, payload.model_dump())


@router.get("/string_reversal_requests/{item_id}", response_model=schemas.StringReversalRequestRead)
def get_string_reversal_request_177(item_id: int, session: Annotated[Session, Depends(get_session)]):
    """Fetch one StringReversalRequest"""
    obj = service.get_string_reversal_request(session, item_id)
    if obj is None:
        raise HTTPException(404, "StringReversalRequest not found")
    return obj


@router.delete("/string_reversal_requests/{item_id}", status_code=204)
def delete_string_reversal_request_389(item_id: int, session: Annotated[Session, Depends(get_session)]):
    """Delete a StringReversalRequest"""
    if not service.delete_string_reversal_request(session, item_id):
        raise HTTPException(404, "StringReversalRequest not found")


@router.get("/string_reversal_responses", response_model=list[schemas.StringReversalResponseRead])
def list_string_reversal_response_128(session: Annotated[Session, Depends(get_session)]):
    """List StringReversalResponse records"""
    return service.list_string_reversal_responses(session)


@router.post("/string_reversal_responses", response_model=schemas.StringReversalResponseRead, status_code=201)
def create_string_reversal_response_398(payload: schemas.StringReversalResponseCreate, session: Annotated[Session, Depends(get_session)]):
    """Create a StringReversalResponse"""
    return service.create_string_reversal_response(session, payload.model_dump())


@router.get("/string_reversal_responses/{item_id}", response_model=schemas.StringReversalResponseRead)
def get_string_reversal_response_346(item_id: int, session: Annotated[Session, Depends(get_session)]):
    """Fetch one StringReversalResponse"""
    obj = service.get_string_reversal_response(session, item_id)
    if obj is None:
        raise HTTPException(404, "StringReversalResponse not found")
    return obj


@router.delete("/string_reversal_responses/{item_id}", status_code=204)
def delete_string_reversal_response_259(item_id: int, session: Annotated[Session, Depends(get_session)]):
    """Delete a StringReversalResponse"""
    if not service.delete_string_reversal_response(session, item_id):
        raise HTTPException(404, "StringReversalResponse not found")
