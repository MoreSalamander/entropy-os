"""Router for export_service. Thin by design: logic lives in the service."""


from fastapi import APIRouter

router = APIRouter(tags=["export_service"])


@router.get("/opportunities/export")
def list_op_590():
    """Export opportunities to CSV (STUB — custom logic not yet implemented)"""
    return {"implemented": False,
            "endpoint": "GET /opportunities/export",
            "summary": "Export opportunities to CSV"}
