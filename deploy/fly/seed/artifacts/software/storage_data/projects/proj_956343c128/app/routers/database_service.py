"""Router for database_service. Thin by design: logic lives in the service."""

from fastapi import APIRouter

router = APIRouter(tags=["database_service"])
