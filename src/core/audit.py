from __future__ import annotations

from sqlalchemy.orm import Session

from src.models.audit import AuditLog


def record_audit_log(
    db: Session,
    *,
    actor_id: str | None,
    object_type: str,
    object_id: str,
    action: str,
    result: str,
    details: dict | None = None,
) -> AuditLog:
    log = AuditLog(
        actor_id=actor_id,
        object_type=object_type,
        object_id=object_id,
        action=action,
        result=result,
        details=details,
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return log
