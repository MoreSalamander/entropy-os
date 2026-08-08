"""Router for quiz_service. Thin by design: logic lives in the service."""

from fastapi import APIRouter

router = APIRouter(tags=["quiz_service"])
