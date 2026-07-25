from fastapi import APIRouter, Depends, HTTPException, status
from redis import Redis
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from src.api.auth.dependencies import require_roles
from src.core.config import settings
from src.core.database import get_db
from src.core.storage import UPLOAD_ROOT
from src.core.time import utc_now
from src.models.editorial import EmailDelivery
from src.models.evaluation import EvaluationWorkUnit
from src.models.user import User

router = APIRouter()


@router.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok", "service": "中国自主知识创新（法学论文）评价系统"}


def _redis() -> Redis:
    return Redis.from_url(
        settings.redis_url,
        socket_connect_timeout=2,
        socket_timeout=2,
        decode_responses=True,
    )


@router.get("/health/live")
def liveness() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready")
def readiness(db: Session = Depends(get_db)) -> dict:
    components: dict[str, str] = {}
    try:
        db.execute(text("SELECT 1"))
        components["database"] = "ok"
    except Exception:
        components["database"] = "failed"
    try:
        _redis().ping()
        components["redis"] = "ok"
    except Exception:
        components["redis"] = "failed"
    try:
        UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
        probe = UPLOAD_ROOT / ".readiness"
        probe.touch(exist_ok=True)
        probe.unlink(missing_ok=True)
        components["storage"] = "ok"
    except OSError:
        components["storage"] = "failed"
    if any(value != "ok" for value in components.values()):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "not_ready", "components": components},
        )
    return {"status": "ready", "components": components}


@router.get("/health/operations")
def operations(
    _: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
) -> dict:
    stale_before = utc_now().timestamp() - settings.task_stale_seconds
    work_counts = dict(
        db.query(EvaluationWorkUnit.status, func.count(EvaluationWorkUnit.id))
        .group_by(EvaluationWorkUnit.status)
        .all()
    )
    email_counts = dict(
        db.query(EmailDelivery.status, func.count(EmailDelivery.id))
        .group_by(EmailDelivery.status)
        .all()
    )
    stale_count = sum(
        1
        for (heartbeat,) in db.query(EvaluationWorkUnit.heartbeat_at)
        .filter(EvaluationWorkUnit.status == "running")
        .all()
        if heartbeat is not None and heartbeat.timestamp() < stale_before
    )
    queue_depth = None
    try:
        queue_depth = int(_redis().llen("celery"))
    except Exception:
        pass
    return {
        "work_units": work_counts,
        "stalled_work_units": stale_count,
        "email_deliveries": email_counts,
        "queue_depth": queue_depth,
    }
