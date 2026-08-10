"""Router for auth_service. Thin by design: logic lives in the service."""


from fastapi import APIRouter

router = APIRouter(tags=["auth_service"])


@router.post("/login")
def create_op_844():
    """Authenticate user credentials (STUB — custom logic not yet implemented)"""
    return {"implemented": False,
            "endpoint": "POST /login",
            "summary": "Authenticate user credentials"}


@router.get("/protected/gate-outcomes")
def list_op_395():
    """Query recorded gate outcomes by filters (authenticated users only) (STUB — custom logic not yet implemented)"""
    return {"implemented": False,
            "endpoint": "GET /protected/gate-outcomes",
            "summary": "Query recorded gate outcomes by filters (authenticated users only)"}
