from __future__ import annotations

import inspect

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from src.api.auth.dependencies import require_roles
from src.api.schemas.admin import AdminTaskActionResponse
from src.core.audit import record_audit_log
from src.core.database import get_db
from src.core.state_machine import ensure_valid_task_transition
from src.models.evaluation import EvaluationTask
from src.models.paper import Paper
from src.models.user import User

router = APIRouter()


async def _dispatch_retry(request: Request, db: Session, task_id: str) -> None:
    pipeline_runner = getattr(request.app.state, "pipeline_runner", None)
    if pipeline_runner is not None:
        result = pipeline_runner(task_id, db)
        if inspect.isawaitable(result):
            await result
        return
    task_dispatcher = getattr(request.app.state, "task_dispatcher", None)
    if task_dispatcher is None:
        raise RuntimeError("No task dispatcher configured")
    task_dispatcher(task_id)


def _load_task_and_paper(db: Session, task_id: str) -> tuple[EvaluationTask, Paper]:
    task = db.get(EvaluationTask, task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    paper = db.get(Paper, task.paper_id)
    if paper is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Paper not found")
    return task, paper


@router.post("/tasks/{task_id}/retry", response_model=AdminTaskActionResponse)
async def retry_task(
    task_id: str,
    request: Request,
    current_user: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
) -> AdminTaskActionResponse:
    task, paper = _load_task_and_paper(db, task_id)
    ensure_valid_task_transition(task.status, "processing")
    task.status = "processing"
    paper.status = "processing"
    task.failure_detail = None
    task.failure_stage = None
    db.add(task)
    db.add(paper)
    db.commit()
    await _dispatch_retry(request, db, task.id)
    db.refresh(task)
    db.refresh(paper)
    record_audit_log(
        db,
        actor_id=current_user.id,
        object_type="evaluation_task",
        object_id=task.id,
        action="retry_task",
        result=task.status,
        details={"paper_id": paper.id},
    )
    return AdminTaskActionResponse(task_id=task.id, task_status=task.status, paper_status=paper.status)


@router.post("/tasks/{task_id}/close", response_model=AdminTaskActionResponse)
def close_task(
    task_id: str,
    current_user: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
) -> AdminTaskActionResponse:
    task, paper = _load_task_and_paper(db, task_id)
    ensure_valid_task_transition(task.status, "closed")
    task.status = "closed"
    paper.status = "closed"
    db.add(task)
    db.add(paper)
    db.commit()
    record_audit_log(
        db,
        actor_id=current_user.id,
        object_type="evaluation_task",
        object_id=task.id,
        action="close_task",
        result="closed",
        details={"paper_id": paper.id},
    )
    return AdminTaskActionResponse(task_id=task.id, task_status=task.status, paper_status=paper.status)
