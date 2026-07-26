from __future__ import annotations

import inspect
import json
from pathlib import Path

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session

from src.api.schemas.admin import BatchStatusResponse
from src.api.auth.dependencies import get_current_user, require_roles
from src.api.schemas.papers import (
    BatchPaperTaskResponse,
    PaperListItemResponse,
    PaperListResponse,
    PaperStatusResponse,
    PaperTaskResponse,
)
from src.core.database import get_db
from src.core.storage import save_upload_file, validate_upload_filename
from src.editorial.access import (
    accessible_unit_ids,
    editor_can_access_paper,
    editorial_submission_for_paper,
)
from src.evaluation.cross_review import CrossReviewService
from src.evaluation.progress import progress_summary
from src.knowledge.loader import load_framework
from src.knowledge.registry import resolve_framework_path
from src.models.batch import BatchTask
from src.models.evaluation import AICallLog, DimensionScore, EvaluationTask
from src.models.editorial import EditorialSubmission
from src.models.paper import Paper
from src.models.reliability import ReliabilityResult
from src.models.report import Report
from src.models.review import ExpertReview
from src.reliability.threshold_checker import summarize_reliability
from src.models.user import User

router = APIRouter()

DEFAULT_FRAMEWORK_PATH = str(resolve_framework_path())
DEFAULT_PROVIDER_NAMES = ["qwen3.6-plus", "kimi-k2.6", "glm-5.1"]


def _parse_provider_names(provider_names: str | None) -> list[str]:
    if not provider_names:
        return DEFAULT_PROVIDER_NAMES
    return [name.strip() for name in provider_names.split(",") if name.strip()]


def _ensure_paper_status_access(
    db: Session,
    current_user: User,
    paper: Paper,
    task: EvaluationTask,
) -> None:
    if current_user.role == "admin":
        return
    if current_user.role == "editor":
        if editor_can_access_paper(db, current_user, paper.id):
            return
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    if current_user.role == "submitter" and paper.uploaded_by == current_user.id:
        return
    if current_user.role == "expert":
        review = (
            db.query(ExpertReview)
            .join(EvaluationTask, ExpertReview.task_id == EvaluationTask.id)
            .filter(
                EvaluationTask.paper_id == paper.id,
                ExpertReview.expert_id == current_user.id,
            )
            .first()
        )
        if review is not None:
            return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权访问")


def _ensure_batch_status_access(
    db: Session, current_user: User, tasks: list[EvaluationTask]
) -> None:
    if current_user.role == "admin":
        return
    if current_user.role == "editor" and all(
        editor_can_access_paper(db, current_user, task.paper_id) for task in tasks
    ):
        return
    if current_user.role == "submitter":
        paper_ids = [task.paper_id for task in tasks]
        if not paper_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="无权访问"
            )
        owned_count = (
            db.query(Paper)
            .filter(Paper.id.in_(paper_ids), Paper.uploaded_by == current_user.id)
            .count()
        )
        if owned_count == len(paper_ids):
            return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权访问")


def _create_task_record(
    db: Session,
    *,
    paper: Paper,
    framework_path: str,
    provider_names: list[str],
    cross_review_enabled: bool = False,
    batch_id: str | None = None,
) -> EvaluationTask:
    framework = load_framework(framework_path)
    if cross_review_enabled:
        CrossReviewService().validate_provider_names(provider_names)
    task = EvaluationTask(
        paper_id=paper.id,
        batch_id=batch_id,
        framework_id=framework.version,
        framework_path=framework_path,
        provider_names=json.dumps(provider_names, ensure_ascii=False),
        status="pending",
        cross_review_enabled=cross_review_enabled,
        final_round=1,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


async def _dispatch_pipeline(
    request: Request,
    db: Session,
    task_id: str,
) -> None:
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


async def _create_paper_and_task(
    request: Request,
    db: Session,
    file: UploadFile,
    current_user: User,
    *,
    framework_path: str,
    provider_names: list[str],
    cross_review_enabled: bool = False,
    batch_id: str | None = None,
) -> PaperTaskResponse:
    if cross_review_enabled:
        try:
            CrossReviewService().validate_provider_names(provider_names)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
            ) from exc
    try:
        ext = validate_upload_filename(file.filename or "")
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc

    paper = Paper(
        original_filename=file.filename or "upload",
        file_type=ext,
        status="pending",
        uploaded_by=current_user.id,
        title=Path(file.filename or "upload").stem,
    )
    db.add(paper)
    db.flush()
    try:
        file_path = await save_upload_file(file, paper.id)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    paper.file_path = str(file_path)
    db.add(paper)
    db.commit()
    db.refresh(paper)

    task = _create_task_record(
        db,
        paper=paper,
        framework_path=framework_path,
        provider_names=provider_names,
        cross_review_enabled=cross_review_enabled,
        batch_id=batch_id,
    )
    await _dispatch_pipeline(request, db, task.id)
    db.refresh(paper)
    db.refresh(task)
    return PaperTaskResponse(
        batch_id=batch_id,
        paper_id=paper.id,
        task_id=task.id,
        paper_status=paper.status,
        task_status=task.status,
    )


@router.post("", response_model=PaperTaskResponse, status_code=status.HTTP_202_ACCEPTED)
async def upload_paper(
    request: Request,
    file: UploadFile = File(...),
    framework_path: str = Form(DEFAULT_FRAMEWORK_PATH),
    provider_names: str | None = Form(default=None),
    cross_review_enabled: bool = Form(default=False),
    current_user: User = Depends(require_roles("editor", "admin")),
    db: Session = Depends(get_db),
) -> PaperTaskResponse:
    return await _create_paper_and_task(
        request,
        db,
        file,
        current_user,
        framework_path=framework_path,
        provider_names=_parse_provider_names(provider_names),
        cross_review_enabled=cross_review_enabled,
    )


@router.get("", response_model=PaperListResponse)
def list_papers(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PaperListResponse:
    query = db.query(Paper)
    if current_user.role == "submitter":
        query = query.filter(Paper.uploaded_by == current_user.id)
    elif current_user.role == "editor":
        editorial_paper_ids = db.query(EditorialSubmission.paper_id)
        allowed_editorial_paper_ids = db.query(EditorialSubmission.paper_id).filter(
            EditorialSubmission.unit_id.in_(accessible_unit_ids(db, current_user))
        )
        query = query.filter(
            ~Paper.id.in_(editorial_paper_ids)
            | Paper.id.in_(allowed_editorial_paper_ids)
        )
    papers = query.order_by(Paper.created_at.desc()).all()
    return PaperListResponse(
        items=[
            PaperListItemResponse(
                paper_id=paper.id,
                title=paper.title,
                original_filename=paper.original_filename,
                paper_status=paper.status,
                precheck_status=paper.precheck_status,
            )
            for paper in papers
        ]
    )


@router.post(
    "/batch",
    response_model=BatchPaperTaskResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def batch_upload_papers(
    request: Request,
    files: list[UploadFile] = File(...),
    framework_path: str = Form(DEFAULT_FRAMEWORK_PATH),
    provider_names: str | None = Form(default=None),
    cross_review_enabled: bool = Form(default=False),
    current_user: User = Depends(require_roles("editor", "admin")),
    db: Session = Depends(get_db),
) -> BatchPaperTaskResponse:
    batch = BatchTask(total=len(files))
    db.add(batch)
    db.commit()
    db.refresh(batch)
    items = []
    parsed_provider_names = _parse_provider_names(provider_names)
    for file in files:
        items.append(
            await _create_paper_and_task(
                request,
                db,
                file,
                current_user,
                framework_path=framework_path,
                provider_names=parsed_provider_names,
                cross_review_enabled=cross_review_enabled,
                batch_id=batch.id,
            )
        )
    return BatchPaperTaskResponse(batch_id=batch.id, total=len(items), items=items)


@router.get("/{paper_id}/status", response_model=PaperStatusResponse)
def get_paper_status(
    paper_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PaperStatusResponse:
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

    _ensure_paper_status_access(db, current_user, paper, task)

    reliability_rows = (
        db.query(ReliabilityResult)
        .filter(
            ReliabilityResult.task_id == task.id,
            ReliabilityResult.round_number == task.final_round,
        )
        .all()
    )
    reliability_summary = None
    if reliability_rows:
        reliability_summary = summarize_reliability(
            [
                type(
                    "ReliabilityRowAdapter",
                    (),
                    {
                        "dimension_key": row.dimension_key,
                        "is_high_confidence": row.is_high_confidence,
                    },
                )()
                for row in reliability_rows
            ]
        )

    return PaperStatusResponse(
        paper_id=paper.id,
        task_id=task.id,
        paper_status=paper.status,
        task_status=task.status,
        precheck_status=paper.precheck_status,
        failure_stage=task.failure_stage,
        failure_detail=task.failure_detail,
        reliability_summary=reliability_summary,
        progress=progress_summary(db, task.id),
    )


@router.get("/batch/{batch_id}/status", response_model=BatchStatusResponse)
def get_batch_status(
    batch_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BatchStatusResponse:
    batch = db.get(BatchTask, batch_id)
    if batch is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="未找到批量任务"
        )
    tasks = db.query(EvaluationTask).filter(EvaluationTask.batch_id == batch.id).all()
    _ensure_batch_status_access(db, current_user, tasks)
    completed = sum(1 for task in tasks if task.status == "completed")
    failed = sum(1 for task in tasks if task.status == "recovering")
    return BatchStatusResponse(
        batch_id=batch.id,
        total=batch.total,
        completed=completed,
        failed=failed,
    )


@router.delete("/{paper_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_paper(
    paper_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    """删除论文及其关联的任务、评分、报告等数据"""
    paper = db.get(Paper, paper_id)
    if paper is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未找到论文")

    if editorial_submission_for_paper(db, paper.id) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="编辑投稿记录不可变，不能在此删除",
        )

    # 权限检查：只有上传者本人或 admin/editor 可以删除
    if current_user.role not in {"admin", "editor"}:
        if current_user.role != "submitter" or paper.uploaded_by != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="无权删除此论文"
            )

    # 获取关联的任务
    tasks = db.query(EvaluationTask).filter(EvaluationTask.paper_id == paper.id).all()

    for task in tasks:
        # 删除专家评审相关数据
        reviews = db.query(ExpertReview).filter(ExpertReview.task_id == task.id).all()
        for review in reviews:
            db.query(ExpertReview).filter(ExpertReview.id == review.id).delete()

        # 删除可靠性结果
        db.query(ReliabilityResult).filter(
            ReliabilityResult.task_id == task.id
        ).delete()

        # 删除维度评分
        db.query(DimensionScore).filter(DimensionScore.task_id == task.id).delete()

        # 删除报告
        db.query(Report).filter(Report.task_id == task.id).delete()

        # 删除 AI 调用日志
        db.query(AICallLog).filter(AICallLog.task_id == task.id).delete()

        # 删除任务
        db.delete(task)

    # 删除文件
    if paper.file_path and Path(paper.file_path).exists():
        Path(paper.file_path).unlink()

    # 删除论文
    db.delete(paper)
    db.commit()
