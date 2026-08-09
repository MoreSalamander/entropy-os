"""Router for auth_service. Thin by design: logic lives in the service."""


from fastapi import APIRouter

router = APIRouter(tags=["auth_service"])


@router.post("/login")
def create_op_539():
    """Login user (STUB — custom logic not yet implemented)"""
    return {"implemented": False,
            "endpoint": "POST /login",
            "summary": "Login user"}


@router.get("/me")
def list_op_358():
    """Get current user (STUB — custom logic not yet implemented)"""
    return {"implemented": False,
            "endpoint": "GET /me",
            "summary": "Get current user"}
