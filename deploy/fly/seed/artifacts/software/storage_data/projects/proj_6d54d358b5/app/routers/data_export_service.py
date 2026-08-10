"""Router for data_export_service. Thin by design: logic lives in the service."""

from fastapi import APIRouter

router = APIRouter(tags=["data_export_service"])
