"""Router for csv_export_service. Thin by design: logic lives in the service."""


from fastapi import APIRouter

router = APIRouter(tags=["csv_export_service"])


@router.get("/exports/{id}")
def get_op_912():
    """Get hunt data in CSV format (STUB — custom logic not yet implemented)"""
    return {"implemented": False,
            "endpoint": "GET /exports/{id}",
            "summary": "Get hunt data in CSV format"}
