"""Router for example_service. Thin by design: logic lives in the service."""


from fastapi import APIRouter

router = APIRouter(tags=["example_service"])


@router.get("/examples/{concept}")
def get_op_217():
    """ (STUB — custom logic not yet implemented)"""
    return {"implemented": False,
            "endpoint": "GET /examples/{concept}",
            "summary": ""}
