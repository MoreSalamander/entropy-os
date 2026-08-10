"""Router for input_limiter_service. Thin by design: logic lives in the service."""


from fastapi import APIRouter

router = APIRouter(tags=["input_limiter_service"])


@router.post("/reverse-string")
def create_op_216():
    """Reverse input string with correct character order (limited length) (STUB — custom logic not yet implemented)"""
    return {"implemented": False,
            "endpoint": "POST /reverse-string",
            "summary": "Reverse input string with correct character order (limited length)"}
