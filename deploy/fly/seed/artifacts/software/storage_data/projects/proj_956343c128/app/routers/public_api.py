"""Router for public_api. Thin by design: logic lives in the service."""


from fastapi import APIRouter

router = APIRouter(tags=["public_api"])


@router.get("/content/{lesson_id}")
def get_op_571():
    """ (STUB — custom logic not yet implemented)"""
    return {"implemented": False,
            "endpoint": "GET /content/{lesson_id}",
            "summary": ""}
