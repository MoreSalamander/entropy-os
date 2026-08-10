"""Router for debugging_service. Thin by design: logic lives in the service."""


from fastapi import APIRouter

router = APIRouter(tags=["debugging_service"])


@router.get("/debugging/input-string")
def list_op_984():
    """Retrieve stored input string for debugging purposes (STUB — custom logic not yet implemented)"""
    return {"implemented": False,
            "endpoint": "GET /debugging/input-string",
            "summary": "Retrieve stored input string for debugging purposes"}
