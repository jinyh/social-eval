from __future__ import annotations

import copy

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from src.api.auth.dependencies import get_current_user
from src.core.audit import record_audit_log
from src.core.database import get_db
from src.editorial.access import editor_can_access_paper
from src.models.evaluation import EvaluationTask
from src.models.paper import Paper
from src.models.review import ExpertReview
from src.models.user import User
from src.reporting.exporters import (
    export_report_json,
    export_report_pdf,
    persist_report_export,
)
from src.reporting.simple_pdf_builder import build_simple_pdf
from src.reporting.versioning import get_current_report

router = APIRouter()


def _load_paper_and_task(db: Session, paper_id: str) -> tuple[Paper, EvaluationTask]:
    paper = db.get(Paper, paper_id)
    if paper is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未找到论文")
    task = (
        db.query(EvaluationTask)
        .filter(EvaluationTask.paper_id == paper.id)
        .order_by(EvaluationTask.created_at.desc())
        .first()
    )
    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="未找到评价任务"
        )
    return paper, task


def _load_paper_and_task_by_id(
    db: Session, paper_id: str, task_id: str | None
) -> tuple[Paper, EvaluationTask]:
    if task_id is None:
        return _load_paper_and_task(db, paper_id)
    paper = db.get(Paper, paper_id)
    if paper is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未找到论文")
    task = db.get(EvaluationTask, task_id)
    if task is None or task.paper_id != paper.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="未找到评价任务"
        )
    return paper, task


def _expert_has_task_access(
    db: Session, current_user: User, task: EvaluationTask
) -> bool:
    return (
        db.query(ExpertReview)
        .filter(
            ExpertReview.task_id == task.id, ExpertReview.expert_id == current_user.id
        )
        .first()
        is not None
    )


def _expert_review_for_task(
    db: Session, current_user: User, task: EvaluationTask
) -> ExpertReview | None:
    if current_user.role != "expert":
        return None
    return (
        db.query(ExpertReview)
        .filter(
            ExpertReview.task_id == task.id,
            ExpertReview.expert_id == current_user.id,
        )
        .first()
    )


def _blind_report_view(report_data: dict) -> dict:
    """专家独立评阅阶段隐藏全部智能分数、分析和模型信息。"""

    payload = copy.deepcopy(report_data)
    payload["review_stage"] = "blind"
    payload["weighted_total"] = None
    payload["precheck_result"] = None
    for dimension in payload.get("dimensions", []):
        dimension.pop("ai", None)
        dimension.pop("analysis", None)
        dimension.pop("summary", None)
        dimension["notice"] = "请先依据匿名稿独立判断。"
    payload.pop("raw_model_outputs", None)
    return payload


def _ensure_public_access(
    db: Session, current_user: User, paper: Paper, task: EvaluationTask
) -> None:
    if current_user.role == "admin":
        return
    if current_user.role == "editor":
        if editor_can_access_paper(db, current_user, paper.id):
            return
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    if current_user.role == "submitter" and paper.uploaded_by == current_user.id:
        return
    if current_user.role == "expert" and _expert_has_task_access(
        db, current_user, task
    ):
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权访问")


def _ensure_internal_access(
    db: Session, current_user: User, task: EvaluationTask
) -> None:
    if current_user.role == "admin":
        return
    if current_user.role == "editor":
        if editor_can_access_paper(db, current_user, task.paper_id):
            return
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    if current_user.role == "expert":
        if _expert_has_task_access(db, current_user, task):
            return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权访问")


@router.get("/{paper_id}/report")
def get_public_report(
    paper_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    paper, task = _load_paper_and_task(db, paper_id)
    _ensure_public_access(db, current_user, paper, task)
    expert_review = _expert_review_for_task(db, current_user, task)
    if expert_review is not None and expert_review.blind_submitted_at is None:
        raise HTTPException(status_code=409, detail="提交独立评阅后才能查看评价报告")
    report = get_current_report(db, task.id, "public")
    return report.report_data


@router.get("/{paper_id}/internal-report")
def get_internal_report(
    paper_id: str,
    task_id: str | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    _, task = _load_paper_and_task_by_id(db, paper_id, task_id)
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
    expert_review = _expert_review_for_task(db, current_user, task)
    if expert_review is not None and expert_review.blind_submitted_at is None:
        return _blind_report_view(report.report_data)
    payload = copy.deepcopy(report.report_data)
    if expert_review is not None:
        payload["review_stage"] = (
            "completed" if expert_review.status == "submitted" else "comparison"
        )
    return payload


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
        _ensure_public_access(db, current_user, paper, task)
    expert_review = _expert_review_for_task(db, current_user, task)
    if expert_review is not None and expert_review.blind_submitted_at is None:
        raise HTTPException(status_code=409, detail="提交独立评阅后才能导出评价报告")

    report = get_current_report(db, task.id, report_type)
    if format == "json":
        content = export_report_json(report)
        persist_report_export(db, report=report, export_type="json", content=content)
        return JSONResponse(content=report.report_data)

    content = export_report_pdf(report)
    persist_report_export(db, report=report, export_type="pdf", content=content)
    return Response(content=content, media_type="application/pdf")


@router.get("/{paper_id}/export/simple")
def export_simple_report(
    paper_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    导出简洁版 PDF 报告（投稿者视图）。

    权限：
    - admin, editor: 可导出所有报告
    - submitter: 只能导出自己上传的稿件
    - expert: 可导出被分配复核的稿件
    """
    paper, task = _load_paper_and_task(db, paper_id)
    _ensure_public_access(db, current_user, paper, task)
    expert_review = _expert_review_for_task(db, current_user, task)
    if expert_review is not None and expert_review.blind_submitted_at is None:
        raise HTTPException(status_code=409, detail="提交独立评阅后才能导出评价报告")

    report = get_current_report(db, task.id, "public")

    # 构建简洁版报告数据
    simple_data = _build_simple_report_data(report.report_data)

    pdf_content = build_simple_pdf(simple_data)

    record_audit_log(
        db,
        actor_id=current_user.id,
        object_type="report",
        object_id=report.id,
        action="simple_export",
        result="success",
        details={"paper_id": paper_id, "export_type": "simple_pdf"},
    )

    return Response(content=pdf_content, media_type="application/pdf")


def _build_simple_report_data(report_data: dict) -> dict:
    """构建简洁版报告数据，过滤掉投稿者不应看到的字段"""
    dimensions = []
    for dim in report_data.get("dimensions", []):
        simple_dim = {
            "name_zh": dim.get("name_zh", dim.get("name_en")),
            "name_en": dim.get("name_en"),
            "ai": {
                "mean_score": dim.get("ai", {}).get("mean_score", 0),
            },
            "summary": dim.get("summary"),
            "analysis": dim.get("analysis"),  # 用于兜底提取
        }
        dimensions.append(simple_dim)

    # 兼容 title 和 paper_title 两种字段名
    title = report_data.get("title") or report_data.get("paper_title")

    return {
        "title": title,
        "weighted_total": report_data.get("weighted_total", 0),
        "conclusion": report_data.get("conclusion"),
        "dimensions": dimensions,
        "expert_conclusion": report_data.get("expert_conclusion"),
    }
