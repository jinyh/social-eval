from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from src.api.auth.dependencies import get_current_user
from src.core.audit import record_audit_log
from src.core.database import get_db
from src.models.evaluation import EvaluationTask
from src.models.paper import Paper
from src.models.review import ExpertReview
from src.models.user import User
from src.reporting.exporters import export_report_json, export_report_pdf, persist_report_export
from src.reporting.versioning import get_current_report

router = APIRouter()


def _load_paper_and_task(db: Session, paper_id: str) -> tuple[Paper, EvaluationTask]:
    paper = db.get(Paper, paper_id)
    if paper is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Paper not found")
    task = (
        db.query(EvaluationTask)
        .filter(EvaluationTask.paper_id == paper.id)
        .order_by(EvaluationTask.created_at.desc())
        .first()
    )
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return paper, task


def _ensure_public_access(current_user: User, paper: Paper) -> None:
    if current_user.role in {"admin", "editor"}:
        return
    if current_user.role == "submitter" and paper.uploaded_by == current_user.id:
        return
    if current_user.role == "expert":
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")


def _ensure_internal_access(db: Session, current_user: User, task: EvaluationTask) -> None:
    if current_user.role in {"admin", "editor"}:
        return
    if current_user.role == "expert":
        review = (
            db.query(ExpertReview)
            .filter(ExpertReview.task_id == task.id, ExpertReview.expert_id == current_user.id)
            .first()
        )
        if review is not None:
            return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")


@router.get("/{paper_id}/report")
def get_public_report(
    paper_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    paper, task = _load_paper_and_task(db, paper_id)
    _ensure_public_access(current_user, paper)
    report = get_current_report(db, task.id, "public")
    return report.report_data


@router.get("/{paper_id}/internal-report")
def get_internal_report(
    paper_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    _, task = _load_paper_and_task(db, paper_id)
    _ensure_internal_access(db, current_user, task)
    report = get_current_report(db, task.id, "internal")
    record_audit_log(
        db,
        actor_id=current_user.id,
        object_type="report",
        object_id=report.id,
        action="internal_report_access",
        result="success",
        details={"paper_id": paper_id, "report_type": "internal"},
    )
    return report.report_data


@router.get("/{paper_id}/report/export")
def export_report(
    paper_id: str,
    format: str = Query(..., pattern="^(json|pdf)$"),
    report_type: str = Query("public", pattern="^(public|internal)$"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    paper, task = _load_paper_and_task(db, paper_id)
    if report_type == "internal":
        _ensure_internal_access(db, current_user, task)
    else:
        _ensure_public_access(current_user, paper)

    report = get_current_report(db, task.id, report_type)
    if format == "json":
        content = export_report_json(report)
        persist_report_export(db, report=report, export_type="json", content=content)
        return JSONResponse(content=report.report_data)

    content = export_report_pdf(report)
    persist_report_export(db, report=report, export_type="pdf", content=content)
    return Response(content=content, media_type="application/pdf")
