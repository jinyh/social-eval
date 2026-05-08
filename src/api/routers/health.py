from fastapi import APIRouter


router = APIRouter()


@router.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok", "service": "中国自主知识创新（法学论文）评价系统"}
