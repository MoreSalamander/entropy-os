"""Router for country_code_repository. Thin by design: logic lives in the service."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import schemas
from app.db import get_session
from app.services import country_code_repository as service

router = APIRouter(tags=["country_code_repository"])


@router.get("/country-codes")
def list_op_242():
    """Get all country codes (STUB — custom logic not yet implemented)"""
    return {"implemented": False,
            "endpoint": "GET /country-codes",
            "summary": "Get all country codes"}


@router.post("/country-code")
def create_op_863():
    """Create a new country code (STUB — custom logic not yet implemented)"""
    return {"implemented": False,
            "endpoint": "POST /country-code",
            "summary": "Create a new country code"}


@router.get("/country_codes", response_model=list[schemas.CountryCodeRead])
def list_country_code_459(session: Annotated[Session, Depends(get_session)]):
    """List CountryCode records"""
    return service.list_country_codes(session)


@router.post("/country_codes", response_model=schemas.CountryCodeRead, status_code=201)
def create_country_code_283(payload: schemas.CountryCodeCreate, session: Annotated[Session, Depends(get_session)]):
    """Create a CountryCode"""
    return service.create_country_code(session, payload.model_dump())


@router.get("/country_codes/{item_id}", response_model=schemas.CountryCodeRead)
def get_country_code_29(item_id: int, session: Annotated[Session, Depends(get_session)]):
    """Fetch one CountryCode"""
    obj = service.get_country_code(session, item_id)
    if obj is None:
        raise HTTPException(404, "CountryCode not found")
    return obj


@router.delete("/country_codes/{item_id}", status_code=204)
def delete_country_code_558(item_id: int, session: Annotated[Session, Depends(get_session)]):
    """Delete a CountryCode"""
    if not service.delete_country_code(session, item_id):
        raise HTTPException(404, "CountryCode not found")
