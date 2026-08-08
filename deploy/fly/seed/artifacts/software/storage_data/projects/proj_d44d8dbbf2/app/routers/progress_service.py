"""Router for progress_service. Thin by design: logic lives in the service."""


from fastapi import APIRouter

router = APIRouter(tags=["progress_service"])


@router.get("/users/{id}/progress")
def list_op_55():
    """Get user progress by ID (STUB — custom logic not yet implemented)"""
    return {"implemented": False,
            "endpoint": "GET /users/{id}/progress",
            "summary": "Get user progress by ID"}


@router.post("/users/{id}/progress")
def create_op_598():
    """Update user progress by ID (STUB — custom logic not yet implemented)"""
    return {"implemented": False,
            "endpoint": "POST /users/{id}/progress",
            "summary": "Update user progress by ID"}
