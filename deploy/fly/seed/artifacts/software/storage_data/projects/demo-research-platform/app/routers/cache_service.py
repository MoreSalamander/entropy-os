"""Router for cache_service. Thin by design: logic lives in the service."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import schemas  # noqa: F401
from app.db import get_session
from app.services import cache_service as service

router = APIRouter(tags=["cache_service"])
