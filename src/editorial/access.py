from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from src.models.editorial import (
    EditorialSubmission,
    EditorialUnit,
    EditorialUnitMembership,
)
from src.models.evaluation import EvaluationTask
from src.models.user import User


def accessible_unit_ids(db: Session, user: User) -> set[str]:
    """返回当前用户可访问的编辑单元集合。管理员使用空集合外的显式分支。"""

    if user.role == "admin":
        return {
            row[0]
            for row in db.query(EditorialUnit.id)
            .filter(EditorialUnit.is_active.is_(True))
            .all()
        }
    return {
        row[0]
        for row in db.query(EditorialUnitMembership.unit_id)
        .filter(
            EditorialUnitMembership.user_id == user.id,
            EditorialUnitMembership.is_active.is_(True),
        )
        .all()
    }


def require_unit_access(db: Session, user: User, unit_id: str) -> EditorialUnit:
    """检查编辑单元权限；越权统一返回 404，避免枚举。"""

    unit = db.get(EditorialUnit, unit_id)
    if unit is None or not unit.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    if user.role != "admin" and unit_id not in accessible_unit_ids(db, user):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return unit


def require_submission_access(
    db: Session, user: User, submission_id: str
) -> EditorialSubmission:
    """按所属编辑单元检查投稿访问权限。"""

    submission = db.get(EditorialSubmission, submission_id)
    if submission is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    require_unit_access(db, user, submission.unit_id)
    return submission


def editorial_submission_for_paper(
    db: Session, paper_id: str
) -> EditorialSubmission | None:
    """返回论文对应的编辑投稿；通用评价论文返回 None。"""

    return (
        db.query(EditorialSubmission)
        .filter(EditorialSubmission.paper_id == paper_id)
        .first()
    )


def editor_can_access_paper(db: Session, user: User, paper_id: str) -> bool:
    """编辑对通用历史评价保持兼容，未公开编辑投稿必须按单元隔离。"""

    if user.role == "admin":
        return True
    submission = editorial_submission_for_paper(db, paper_id)
    if submission is None:
        return user.role == "editor"
    return user.role == "editor" and submission.unit_id in accessible_unit_ids(db, user)


def editor_can_access_task(db: Session, user: User, task_id: str) -> bool:
    """按任务关联的投稿检查编辑单元权限。"""

    task = db.get(EvaluationTask, task_id)
    return bool(task and editor_can_access_paper(db, user, task.paper_id))
