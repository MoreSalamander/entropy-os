"""Router for auth_service. Thin by design: logic lives in the service."""


from fastapi import APIRouter

router = APIRouter(tags=["auth_service"])


@router.post("/login")
def create_op_844():
    """Login user (STUB — custom logic not yet implemented)"""
    return {"implemented": False,
            "endpoint": "POST /login",
            "summary": "Login user"}


@router.get("/logout")
def list_op_258():
    """Logout user (STUB — custom logic not yet implemented)"""
    return {"implemented": False,
            "endpoint": "GET /logout",
            "summary": "Logout user"}
