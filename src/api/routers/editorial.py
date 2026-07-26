from __future__ import annotations

import hashlib
import inspect
import json
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.api.auth.dependencies import require_roles
from src.api.schemas.editorial import (
    AnonymousManuscriptResponse,
    AnonymizationConfirmRequest,
    AssignmentRequest,
    EditorialBatchCreateResponse,
    EditorialDecisionCreateRequest,
    EditorialDecisionResponse,
    EditorialOpinionResponse,
    EditorialPolicyValidationDecisionRequest,
    EditorialSubmissionCreateResponse,
    EditorialSubmissionDetailResponse,
    EditorialSubmissionListItem,
    EditorialSubmissionListResponse,
    EditorialUnitListResponse,
    EditorialUnitResponse,
    EditorOpinionRequest,
    GateContinueRequest,
)
from src.core.audit import record_audit_log
from src.core.config import settings
from src.core.database import get_db
from src.core.email import send_editorial_event_email
from src.core.storage import save_upload_file, validate_upload_filename
from src.core.time import utc_now
from src.editorial.access import (
    accessible_unit_ids,
    require_submission_access,
    require_unit_access,
)
from src.editorial.constants import SUBMISSION_STATUS_GROUPS
from src.editorial.manuscript import load_anonymous_manuscript
from src.editorial.policy import (
    resolve_submission_policy,
    resolve_unit_policy,
)
from src.editorial.presentation import (
    build_ccb_summary,
    build_position_summary,
    build_six_dimension_summary,
    localize_synthesis_payload,
)
from src.editorial.reporting import generate_editorial_report
from src.evaluation.cross_review import CrossReviewService
from src.evaluation.progress import progress_summary
from src.knowledge.loader import load_framework
from src.knowledge.registry import resolve_framework_path
from src.models.editorial import (
    EditorialDecision,
    EditorialDocument,
    EditorialOpinion,
    EditorialPolicyVersion,
    EditorialSubmission,
    EditorialUnit,
    EditorialUnitMembership,
    Journal,
    Notification,
    PositionAssessment,
    ValidationRun,
)
from src.models.evaluation import DimensionScore, EvaluationTask
from src.models.paper import Paper
from src.models.reliability import ReliabilityResult
from src.models.review import ExpertReview, ReviewComment
from src.models.user import User

router = APIRouter()


async def _dispatch(request: Request, db: Session, submission_id: str) -> None:
    runner = getattr(request.app.state, "editorial_pipeline_runner", None)
    if runner is not None:
        result = runner(submission_id, db)
        if inspect.isawaitable(result):
            await result
        return
    dispatcher = getattr(request.app.state, "editorial_dispatcher", None)
    if dispatcher is None:
        raise RuntimeError("No editorial dispatcher configured")
    dispatcher(submission_id)


def _unit_response(db: Session, unit: EditorialUnit) -> EditorialUnitResponse:
    journal = db.get(Journal, unit.journal_id)
    return EditorialUnitResponse(
        id=unit.id,
        journal_id=unit.journal_id,
        journal_name=journal.name if journal else "",
        code=unit.code,
        name=unit.name,
        policy_key=unit.policy_key,
        policy_version=unit.policy_version,
        rollout_state=unit.rollout_state,
        trial_policy_version_id=unit.trial_policy_version_id,
        active_policy_version_id=unit.active_policy_version_id,
    )


@router.get("/units", response_model=EditorialUnitListResponse)
def list_editorial_units(
    current_user: User = Depends(require_roles("editor", "admin")),
    db: Session = Depends(get_db),
) -> EditorialUnitListResponse:
    unit_ids = accessible_unit_ids(db, current_user)
    if not unit_ids:
        return EditorialUnitListResponse(items=[])
    units = (
        db.query(EditorialUnit)
        .filter(EditorialUnit.id.in_(unit_ids), EditorialUnit.is_active.is_(True))
        .order_by(EditorialUnit.name)
        .all()
    )
    return EditorialUnitListResponse(items=[_unit_response(db, unit) for unit in units])


def _require_unit_admin_membership(
    db: Session,
    user: User,
    unit_id: str,
) -> EditorialUnitMembership:
    membership = (
        db.query(EditorialUnitMembership)
        .filter(
            EditorialUnitMembership.unit_id == unit_id,
            EditorialUnitMembership.user_id == user.id,
            EditorialUnitMembership.membership_role == "unit_admin",
            EditorialUnitMembership.is_active.is_(True),
        )
        .first()
    )
    if membership is None:
        raise HTTPException(status_code=403, detail="只有单元负责人可以签署策略")
    return membership


def _policy_review_payload(
    db: Session,
    row: EditorialPolicyVersion,
) -> dict:
    snapshot = row.snapshot
    if isinstance(snapshot, str):
        snapshot = json.loads(snapshot)
    validations = (
        db.query(ValidationRun)
        .filter(ValidationRun.policy_version_id == row.id)
        .order_by(ValidationRun.created_at.desc())
        .all()
    )
    return {
        "id": row.id,
        "unit_id": row.unit_id,
        "policy_key": row.policy_key,
        "version": row.version,
        "status": row.status,
        "profile": snapshot["profile"],
        "model_set_version": snapshot["model_set_version"],
        "review_protocol_version": snapshot["review_protocol_version"],
        "framework_version": snapshot["framework_version"],
        "provider_names": snapshot["provider_names"],
        "content_sha256": row.content_sha256,
        "based_on_id": row.based_on_id,
        "created_by": row.created_by,
        "activated_by": row.activated_by,
        "created_at": row.created_at,
        "frozen_at": row.frozen_at,
        "activated_at": row.activated_at,
        "validations": [
            {
                "id": validation.id,
                "validation_type": validation.validation_type,
                "sample_count": validation.sample_count,
                "sample_manifest_sha256": validation.sample_manifest_sha256,
                "metrics": validation.metrics,
                "status": validation.status,
                "signed_by": validation.signed_by,
                "signed_at": validation.signed_at,
                "signer_membership_role": validation.signer_membership_role,
                "rejection_reason": validation.rejection_reason,
                "unit_id": validation.unit_id,
                "framework_version": validation.framework_version,
                "model_set_version": validation.model_set_version,
                "policy_version_id": validation.policy_version_id,
                "created_at": validation.created_at,
            }
            for validation in validations
        ],
    }


@router.get("/policy-versions/pending-signature")
def list_pending_policy_signatures(
    current_user: User = Depends(require_roles("editor")),
    db: Session = Depends(get_db),
) -> dict:
    memberships = (
        db.query(EditorialUnitMembership)
        .filter(
            EditorialUnitMembership.user_id == current_user.id,
            EditorialUnitMembership.membership_role == "unit_admin",
            EditorialUnitMembership.is_active.is_(True),
        )
        .all()
    )
    unit_ids = [membership.unit_id for membership in memberships]
    if not unit_ids:
        return {"items": []}
    rows = (
        db.query(EditorialPolicyVersion)
        .filter(
            EditorialPolicyVersion.unit_id.in_(unit_ids),
            EditorialPolicyVersion.status == "trial",
        )
        .order_by(EditorialPolicyVersion.created_at.desc())
        .all()
    )
    return {"items": [_policy_review_payload(db, row) for row in rows]}


@router.get("/policy-versions/{version_id}/review")
def get_policy_version_review(
    version_id: str,
    current_user: User = Depends(require_roles("editor")),
    db: Session = Depends(get_db),
) -> dict:
    row = db.get(EditorialPolicyVersion, version_id)
    if row is None:
        raise HTTPException(status_code=404, detail="未找到策略版本")
    require_unit_access(db, current_user, row.unit_id)
    return _policy_review_payload(db, row)


@router.post("/validation-runs/{run_id}/decision")
def decide_validation_run(
    run_id: str,
    payload: EditorialPolicyValidationDecisionRequest,
    current_user: User = Depends(require_roles("editor")),
    db: Session = Depends(get_db),
) -> dict:
    row = db.get(ValidationRun, run_id)
    if row is None or row.unit_id is None or row.policy_version_id is None:
        raise HTTPException(status_code=404, detail="未找到可签署的策略验证记录")
    membership = _require_unit_admin_membership(db, current_user, row.unit_id)
    policy_version = db.get(EditorialPolicyVersion, row.policy_version_id)
    if policy_version is None or policy_version.status != "trial":
        raise HTTPException(status_code=409, detail="策略版本不处于试运行状态")
    if row.status == "signed":
        raise HTTPException(status_code=409, detail="验证记录已经签署")
    row.signed_by = current_user.id
    row.signer_membership_role = membership.membership_role
    row.signed_at = utc_now()
    row.rejection_reason = None if payload.approved else payload.reason
    row.status = "signed" if payload.approved else "rejected"
    db.add(row)
    db.commit()
    record_audit_log(
        db,
        actor_id=current_user.id,
        object_type="validation_run",
        object_id=row.id,
        action="editor_validation_decision",
        result=row.status,
        details={
            "policy_version_id": row.policy_version_id,
            "reason": payload.reason,
        },
    )
    return {
        "id": row.id,
        "status": row.status,
        "signed_by": row.signed_by,
        "signed_at": row.signed_at,
        "signer_membership_role": row.signer_membership_role,
        "rejection_reason": row.rejection_reason,
    }


@router.get("/notifications")
def list_notifications(
    current_user: User = Depends(require_roles("editor", "expert", "admin")),
    db: Session = Depends(get_db),
) -> dict:
    rows = (
        db.query(Notification)
        .filter(Notification.user_id == current_user.id)
        .order_by(Notification.created_at.desc())
        .limit(100)
        .all()
    )
    return {
        "items": [
            {
                "id": row.id,
                "event_type": row.event_type,
                "object_type": row.object_type,
                "object_id": row.object_id,
                "payload": row.payload,
                "read_at": row.read_at,
                "created_at": row.created_at,
            }
            for row in rows
        ]
    }


@router.post("/notifications/{notification_id}/read")
def mark_notification_read(
    notification_id: str,
    current_user: User = Depends(require_roles("editor", "expert", "admin")),
    db: Session = Depends(get_db),
) -> dict:
    row = db.get(Notification, notification_id)
    if row is None or row.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="未找到通知")
    if row.read_at is None:
        row.read_at = utc_now()
        db.commit()
    return {"id": row.id, "read_at": row.read_at}


async def _create_submission(
    request: Request,
    db: Session,
    *,
    unit: EditorialUnit,
    file: UploadFile,
    external_manuscript_id: str | None,
    current_user: User,
) -> EditorialSubmissionCreateResponse:
    if external_manuscript_id and (
        db.query(EditorialSubmission)
        .filter(
            EditorialSubmission.unit_id == unit.id,
            EditorialSubmission.external_manuscript_id == external_manuscript_id,
        )
        .first()
        is not None
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="该外部稿号已存在于当前编辑单元",
        )
    try:
        extension = validate_upload_filename(file.filename or "")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    framework_path = str(resolve_framework_path())
    framework = load_framework(framework_path)
    policy, policy_version = resolve_unit_policy(db, unit)
    provider_names = list(policy.provider_names)
    CrossReviewService.for_model_set(
        policy.model_set_version,
        policy.review_protocol_version,
    ).validate_provider_names(provider_names)
    paper = Paper(
        title=Path(file.filename or "upload").stem,
        original_filename=file.filename or "upload",
        file_type=extension,
        status="pending",
        uploaded_by=current_user.id,
    )
    db.add(paper)
    db.flush()
    try:
        file_path = await save_upload_file(file, paper.id)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    paper.file_path = str(file_path)
    task = EvaluationTask(
        paper_id=paper.id,
        framework_id=framework.version,
        framework_path=framework_path,
        provider_names=json.dumps(provider_names, ensure_ascii=False),
        model_set_version=policy.model_set_version,
        review_protocol_version=policy.review_protocol_version,
        run_role="production",
        status="pending",
        cross_review_enabled=True,
        final_round=1,
    )
    db.add(task)
    db.flush()
    responsible_editor_id = None
    if current_user.role == "editor":
        membership = (
            db.query(EditorialUnitMembership)
            .filter(
                EditorialUnitMembership.unit_id == unit.id,
                EditorialUnitMembership.user_id == current_user.id,
                EditorialUnitMembership.is_active.is_(True),
            )
            .first()
        )
        if membership is not None:
            responsible_editor_id = current_user.id
    submission = EditorialSubmission(
        unit_id=unit.id,
        paper_id=paper.id,
        evaluation_task_id=task.id,
        external_manuscript_id=external_manuscript_id or None,
        title=paper.title,
        responsible_editor_id=responsible_editor_id,
        recommendation_state="shadow",
        policy_key=unit.policy_key,
        policy_version=policy.version,
        policy_version_id=policy_version.id if policy_version else None,
        created_by=current_user.id,
    )
    db.add(submission)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="该外部稿号已存在于当前编辑单元",
        ) from exc
    digest = hashlib.sha256(file_path.read_bytes()).hexdigest()
    db.add(
        EditorialDocument(
            submission_id=submission.id,
            kind="original",
            version=1,
            file_path=str(file_path),
            sha256=digest,
        )
    )
    db.commit()
    record_audit_log(
        db,
        actor_id=current_user.id,
        object_type="editorial_submission",
        object_id=submission.id,
        action="create_submission",
        result="queued",
        details={"unit_id": unit.id, "paper_id": paper.id},
    )
    await _dispatch(request, db, submission.id)
    db.refresh(submission)
    return EditorialSubmissionCreateResponse(
        submission_id=submission.id,
        paper_id=paper.id,
        task_id=task.id,
        status=submission.status,
    )


@router.post(
    "/submissions",
    response_model=EditorialSubmissionCreateResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_submission(
    request: Request,
    unit_id: str = Form(...),
    file: UploadFile = File(...),
    external_manuscript_id: str | None = Form(default=None),
    current_user: User = Depends(require_roles("editor", "admin")),
    db: Session = Depends(get_db),
) -> EditorialSubmissionCreateResponse:
    unit = require_unit_access(db, current_user, unit_id)
    return await _create_submission(
        request,
        db,
        unit=unit,
        file=file,
        external_manuscript_id=external_manuscript_id,
        current_user=current_user,
    )


@router.post(
    "/submissions/batch",
    response_model=EditorialBatchCreateResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_submission_batch(
    request: Request,
    unit_id: str = Form(...),
    files: list[UploadFile] = File(...),
    current_user: User = Depends(require_roles("editor", "admin")),
    db: Session = Depends(get_db),
) -> EditorialBatchCreateResponse:
    unit = require_unit_access(db, current_user, unit_id)
    items = [
        await _create_submission(
            request,
            db,
            unit=unit,
            file=file,
            external_manuscript_id=None,
            current_user=current_user,
        )
        for file in files
    ]
    return EditorialBatchCreateResponse(total=len(items), items=items)


@router.get("/submissions", response_model=EditorialSubmissionListResponse)
def list_submissions(
    unit_id: str | None = None,
    submission_status: str | None = None,
    query_text: str | None = Query(default=None, alias="q", max_length=200),
    status_group: str | None = Query(default=None),
    submitted_from: date | None = Query(default=None),
    submitted_to: date | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(require_roles("editor", "admin")),
    db: Session = Depends(get_db),
) -> EditorialSubmissionListResponse:
    unit_ids = accessible_unit_ids(db, current_user)
    if unit_id:
        require_unit_access(db, current_user, unit_id)
        unit_ids = {unit_id}
    if not unit_ids:
        return EditorialSubmissionListResponse(
            items=[],
            total=0,
            page=page,
            page_size=page_size,
            status_counts={key: 0 for key in SUBMISSION_STATUS_GROUPS},
        )
    base_query = db.query(EditorialSubmission).filter(
        EditorialSubmission.unit_id.in_(unit_ids)
    )
    if query_text and query_text.strip():
        pattern = f"%{query_text.strip()}%"
        base_query = base_query.filter(
            or_(
                EditorialSubmission.title.ilike(pattern),
                EditorialSubmission.external_manuscript_id.ilike(pattern),
            )
        )
    shanghai = ZoneInfo("Asia/Shanghai")
    if submitted_from:
        local_start = datetime.combine(submitted_from, time.min, tzinfo=shanghai)
        utc_start = local_start.astimezone(timezone.utc).replace(tzinfo=None)
        base_query = base_query.filter(EditorialSubmission.created_at >= utc_start)
    if submitted_to:
        local_end = datetime.combine(
            submitted_to + timedelta(days=1),
            time.min,
            tzinfo=shanghai,
        )
        utc_end = local_end.astimezone(timezone.utc).replace(tzinfo=None)
        base_query = base_query.filter(EditorialSubmission.created_at < utc_end)

    status_counts = {
        key: base_query.filter(EditorialSubmission.status.in_(statuses)).count()
        for key, statuses in SUBMISSION_STATUS_GROUPS.items()
    }
    filtered_query = base_query
    if submission_status:
        filtered_query = filtered_query.filter(
            EditorialSubmission.status == submission_status
        )
    if status_group:
        statuses = SUBMISSION_STATUS_GROUPS.get(status_group)
        if statuses is None:
            raise HTTPException(status_code=422, detail="未知投稿状态组")
        filtered_query = filtered_query.filter(EditorialSubmission.status.in_(statuses))
    total = filtered_query.count()
    rows = (
        filtered_query.order_by(EditorialSubmission.updated_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return EditorialSubmissionListResponse(
        items=[EditorialSubmissionListItem.model_validate(row) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
        status_counts=status_counts,
    )


@router.get(
    "/submissions/{submission_id}",
    response_model=EditorialSubmissionDetailResponse,
)
def get_submission(
    submission_id: str,
    current_user: User = Depends(require_roles("editor", "admin")),
    db: Session = Depends(get_db),
) -> EditorialSubmissionDetailResponse:
    """返回编辑所需的中文聚合视图，实际模型名仅向管理员开放。"""

    submission = require_submission_access(db, current_user, submission_id)
    paper = db.get(Paper, submission.paper_id)
    task = db.get(EvaluationTask, submission.evaluation_task_id)
    if paper is None or task is None:
        raise HTTPException(status_code=404)
    if current_user.role == "admin":
        record_audit_log(
            db,
            actor_id=current_user.id,
            object_type="editorial_submission",
            object_id=submission.id,
            action="admin_submission_content_access",
            result="allowed",
            details={"unit_id": submission.unit_id},
        )
    scores = (
        db.query(DimensionScore)
        .filter(
            DimensionScore.task_id == task.id,
            DimensionScore.round_number == task.final_round,
        )
        .all()
    )
    reliability = (
        db.query(ReliabilityResult)
        .filter(
            ReliabilityResult.task_id == task.id,
            ReliabilityResult.round_number == task.final_round,
        )
        .all()
    )
    position = (
        db.query(PositionAssessment)
        .filter(PositionAssessment.submission_id == submission.id)
        .order_by(PositionAssessment.version.desc())
        .first()
    )
    opinions = (
        db.query(EditorialOpinion)
        .filter(EditorialOpinion.submission_id == submission.id)
        .order_by(
            EditorialOpinion.opinion_type.desc(),
            EditorialOpinion.version,
            EditorialOpinion.sequence,
        )
        .all()
    )
    decisions = (
        db.query(EditorialDecision)
        .filter(EditorialDecision.submission_id == submission.id)
        .order_by(EditorialDecision.version)
        .all()
    )
    policy = resolve_submission_policy(db, submission)
    provider_names = json.loads(task.provider_names or "[]")
    framework = load_framework(task.framework_path or str(resolve_framework_path()))
    six_dimension_summary = build_six_dimension_summary(
        scores,
        reliability,
        policy,
        provider_names,
        [(dimension.key, dimension.name_zh) for dimension in framework.dimensions],
    )

    documents: dict[str, str] = {}
    document_rows = (
        db.query(EditorialDocument)
        .filter(
            EditorialDocument.submission_id == submission.id,
            EditorialDocument.kind.in_(("original", "anonymized")),
        )
        .order_by(EditorialDocument.version.desc())
        .all()
    )
    for row in document_rows:
        documents.setdefault(
            row.kind,
            f"/api/editorial/submissions/{submission.id}/documents/{row.kind}",
        )

    expert_reviews = []
    for review in (
        db.query(ExpertReview)
        .filter(ExpertReview.task_id == task.id)
        .order_by(ExpertReview.created_at)
        .all()
    ):
        comments = (
            db.query(ReviewComment)
            .filter(ReviewComment.review_id == review.id)
            .order_by(ReviewComment.dimension_key)
            .all()
        )
        expert_reviews.append(
            {
                "review_id": review.id,
                "status": review.status,
                "blind_submitted_at": review.blind_submitted_at,
                "ai_revealed_at": review.ai_revealed_at,
                "completed_at": review.completed_at,
                "comments": [
                    {
                        "dimension_key": item.dimension_key,
                        "expert_score": item.expert_score,
                        "reason": item.reason,
                        "statement_decisions": item.statement_decisions,
                        "comparison_reason": item.comparison_reason,
                    }
                    for item in comments
                ],
            }
        )

    return EditorialSubmissionDetailResponse(
        **EditorialSubmissionListItem.model_validate(submission).model_dump(),
        paper_id=paper.id,
        task_id=task.id,
        anonymization_status=submission.anonymization_status,
        anonymization_result=submission.anonymization_result,
        formal_check_status=submission.formal_check_status,
        formal_check_result=submission.formal_check_result,
        precheck_status=paper.precheck_status,
        precheck_result=paper.precheck_result,
        fit_status=submission.fit_status,
        fit_result=submission.fit_result,
        internal_candidate_decision=(
            submission.internal_candidate_decision
            if submission.recommendation_state == "ready"
            else None
        ),
        manual_review_requested=task.manual_review_requested,
        six_dimension=[
            {
                "dimension_key": row.dimension_key,
                "model_name": (
                    row.model_name if current_user.role == "admin" else "匿名模型"
                ),
                "score": row.score,
                "band": (row.structured_payload or {}).get("band")
                or (row.structured_payload or {}).get("revised_band"),
                "evidence_quotes": row.evidence_quotes,
            }
            for row in scores
        ],
        six_dimension_summary=six_dimension_summary,
        ccb_summary=build_ccb_summary(paper.aggregate_result),
        position_summary=build_position_summary(
            position.result_data if position else None,
            precheck_result=paper.precheck_result,
        ),
        position_assessment=position.result_data if position else None,
        model_set_version=task.model_set_version,
        review_protocol_version=task.review_protocol_version,
        review_protocol_label=(
            "四模型匿名互评"
            if task.review_protocol_version == "six_dimension_peer_review"
            else "分组交叉复核"
        ),
        progress=progress_summary(db, task.id),
        documents=documents,
        expert_reviews=expert_reviews,
        opinions=[
            EditorialOpinionResponse(
                **{
                    **EditorialOpinionResponse.model_validate(opinion).model_dump(),
                    "content": (
                        localize_synthesis_payload(opinion.content)
                        if opinion.opinion_type == "ai_synthesis"
                        else opinion.content
                    ),
                    "model_name": (
                        opinion.model_name if current_user.role == "admin" else None
                    ),
                }
            )
            for opinion in opinions
        ],
        decisions=[
            EditorialDecisionResponse.model_validate(decision) for decision in decisions
        ],
    )


@router.get("/submissions/{submission_id}/documents/{kind}")
def get_submission_document(
    submission_id: str,
    kind: str,
    current_user: User = Depends(require_roles("editor", "admin")),
    db: Session = Depends(get_db),
):
    """下载原稿或匿名稿，并记录内容访问审计。"""

    submission = require_submission_access(db, current_user, submission_id)
    if kind not in {"original", "anonymized"}:
        raise HTTPException(status_code=404, detail="未找到指定稿件版本")
    document = (
        db.query(EditorialDocument)
        .filter(
            EditorialDocument.submission_id == submission.id,
            EditorialDocument.kind == kind,
        )
        .order_by(EditorialDocument.version.desc())
        .first()
    )
    if document is None or not Path(document.file_path).exists():
        raise HTTPException(status_code=404, detail="稿件文件不存在")
    record_audit_log(
        db,
        actor_id=current_user.id,
        object_type="editorial_document",
        object_id=document.id,
        action="download_editorial_document",
        result="allowed",
        details={"submission_id": submission.id, "kind": kind},
    )
    return FileResponse(
        document.file_path,
        filename=Path(document.file_path).name,
        media_type="text/plain" if kind == "anonymized" else None,
    )


@router.get(
    "/submissions/{submission_id}/manuscript",
    response_model=AnonymousManuscriptResponse,
)
def get_submission_manuscript(
    submission_id: str,
    response: Response,
    current_user: User = Depends(require_roles("editor", "admin")),
    db: Session = Depends(get_db),
) -> AnonymousManuscriptResponse:
    """编辑在网页中预览待确认或已确认的匿名稿。"""

    submission = require_submission_access(db, current_user, submission_id)
    task = (
        db.get(EvaluationTask, submission.evaluation_task_id)
        if submission.evaluation_task_id
        else None
    )
    try:
        payload = load_anonymous_manuscript(
            db,
            submission=submission,
            task=task,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    record_audit_log(
        db,
        actor_id=current_user.id,
        object_type="editorial_document",
        object_id=submission.id,
        action="preview_anonymized_editorial_document",
        result="allowed",
        details={"document_version": payload["document_version"]},
    )
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return AnonymousManuscriptResponse(**payload)


@router.post("/submissions/{submission_id}/confirm-anonymization")
async def confirm_anonymization(
    submission_id: str,
    payload: AnonymizationConfirmRequest,
    request: Request,
    current_user: User = Depends(require_roles("editor", "admin")),
    db: Session = Depends(get_db),
) -> dict:
    submission = require_submission_access(db, current_user, submission_id)
    if submission.status != "awaiting_anonymization_confirmation":
        raise HTTPException(status_code=409, detail="当前稿件不处于匿名化确认阶段")
    anonymization_result = dict(submission.anonymization_result or {})
    anonymization_result.update(
        {
            "human_confirmed": True,
            "confirmed_by": current_user.id,
            "confirmed_at": utc_now().isoformat(),
            "confirmation_reason": payload.reason,
        }
    )
    submission.anonymization_result = anonymization_result
    submission.anonymization_status = "confirmed"
    submission.status = "queued"
    db.commit()
    record_audit_log(
        db,
        actor_id=current_user.id,
        object_type="editorial_submission",
        object_id=submission.id,
        action="confirm_anonymization",
        result="confirmed",
        details={"reason": payload.reason},
    )
    await _dispatch(request, db, submission.id)
    db.refresh(submission)
    return {"submission_id": submission.id, "status": submission.status}


@router.post("/submissions/{submission_id}/continue")
async def continue_after_gate(
    submission_id: str,
    payload: GateContinueRequest,
    request: Request,
    current_user: User = Depends(require_roles("editor", "admin")),
    db: Session = Depends(get_db),
) -> dict:
    submission = require_submission_access(db, current_user, submission_id)
    expected = {
        "formal_check": "awaiting_formal_check_confirmation",
        "precheck": "awaiting_precheck_confirmation",
        "journal_fit": "awaiting_fit_confirmation",
    }[payload.stage]
    if submission.status != expected:
        raise HTTPException(status_code=409, detail="当前稿件不处于指定确认阶段")
    if payload.stage == "formal_check":
        submission.formal_check_override_reason = payload.reason
    elif payload.stage == "precheck":
        submission.precheck_override_reason = payload.reason
    else:
        submission.fit_override_reason = payload.reason
    submission.status = "queued"
    db.commit()
    record_audit_log(
        db,
        actor_id=current_user.id,
        object_type="editorial_submission",
        object_id=submission.id,
        action=f"continue_after_{payload.stage}",
        result="queued",
        details={"reason": payload.reason},
    )
    await _dispatch(request, db, submission.id)
    db.refresh(submission)
    return {"submission_id": submission.id, "status": submission.status}


@router.post("/submissions/{submission_id}/assign")
def assign_responsible_editor(
    submission_id: str,
    payload: AssignmentRequest,
    current_user: User = Depends(require_roles("editor", "admin")),
    db: Session = Depends(get_db),
) -> dict:
    submission = require_submission_access(db, current_user, submission_id)
    target = (
        db.query(EditorialUnitMembership)
        .filter(
            EditorialUnitMembership.unit_id == submission.unit_id,
            EditorialUnitMembership.user_id == payload.responsible_editor_id,
            EditorialUnitMembership.is_active.is_(True),
        )
        .first()
    )
    if target is None:
        raise HTTPException(
            status_code=400, detail="目标用户不是当前编辑单元的有效成员"
        )
    previous = submission.responsible_editor_id
    submission.responsible_editor_id = payload.responsible_editor_id
    db.add(
        Notification(
            user_id=payload.responsible_editor_id,
            event_type="responsible_editor_transferred",
            object_type="editorial_submission",
            object_id=submission.id,
            payload={"submission_id": submission.id},
        )
    )
    db.commit()
    target_user = db.get(User, payload.responsible_editor_id)
    if target_user is not None:
        send_editorial_event_email(
            db=db,
            recipient_email=target_user.email,
            submission_id=submission.id,
            event_type="responsible_editor_transferred",
        )
    record_audit_log(
        db,
        actor_id=current_user.id,
        object_type="editorial_submission",
        object_id=submission.id,
        action="transfer_responsible_editor",
        result="assigned",
        details={
            "from": previous,
            "to": payload.responsible_editor_id,
            "reason": payload.reason,
        },
    )
    return {
        "submission_id": submission.id,
        "responsible_editor_id": payload.responsible_editor_id,
    }


@router.post(
    "/submissions/{submission_id}/opinions/editor",
    response_model=EditorialOpinionResponse,
)
def save_editor_opinion(
    submission_id: str,
    payload: EditorOpinionRequest,
    current_user: User = Depends(require_roles("editor", "admin")),
    db: Session = Depends(get_db),
) -> EditorialOpinionResponse:
    submission = require_submission_access(db, current_user, submission_id)
    if (
        current_user.role != "admin"
        and submission.responsible_editor_id != current_user.id
    ):
        raise HTTPException(status_code=403, detail="只有责任编辑可以编辑该意见")
    latest = (
        db.query(EditorialOpinion)
        .filter(
            EditorialOpinion.submission_id == submission.id,
            EditorialOpinion.opinion_type == "editor_final",
        )
        .order_by(EditorialOpinion.version.desc())
        .first()
    )
    if latest is not None and latest.is_locked:
        raise HTTPException(status_code=409, detail="编辑意见已经锁定")
    version = (latest.version + 1) if latest else 1
    opinion = EditorialOpinion(
        submission_id=submission.id,
        opinion_type="editor_final",
        version=version,
        sequence=1,
        content=payload.content,
        created_by=current_user.id,
        is_locked=payload.submit,
    )
    db.add(opinion)
    db.commit()
    db.refresh(opinion)
    return EditorialOpinionResponse.model_validate(opinion)


@router.post(
    "/submissions/{submission_id}/decision",
    response_model=EditorialDecisionResponse,
)
def submit_decision(
    submission_id: str,
    payload: EditorialDecisionCreateRequest,
    current_user: User = Depends(require_roles("editor", "admin")),
    db: Session = Depends(get_db),
) -> EditorialDecisionResponse:
    submission = require_submission_access(db, current_user, submission_id)
    if (
        current_user.role != "admin"
        and submission.responsible_editor_id != current_user.id
    ):
        raise HTTPException(status_code=403, detail="只有责任编辑可以提交决定")
    task = db.get(EvaluationTask, submission.evaluation_task_id)
    if task is None:
        raise HTTPException(status_code=404)
    latest = (
        db.query(EditorialDecision)
        .filter(EditorialDecision.submission_id == submission.id)
        .order_by(EditorialDecision.version.desc())
        .first()
    )
    locked_for_stage = (
        db.query(EditorialDecision)
        .filter(
            EditorialDecision.submission_id == submission.id,
            EditorialDecision.decision_stage == payload.decision_stage,
            EditorialDecision.is_locked.is_(True),
        )
        .first()
    )
    if locked_for_stage is not None:
        raise HTTPException(status_code=409, detail="该阶段决定已经锁定")
    if payload.decision_stage == "final":
        pre_review_decision = (
            db.query(EditorialDecision)
            .filter(
                EditorialDecision.submission_id == submission.id,
                EditorialDecision.decision_stage == "pre_review",
                EditorialDecision.is_locked.is_(True),
            )
            .order_by(EditorialDecision.version.desc())
            .first()
        )
        if pre_review_decision is None or pre_review_decision.final_decision not in {
            "send_external_review",
            "priority_external_review",
        }:
            raise HTTPException(
                status_code=409,
                detail="只有已经送外审的稿件可以提交终审决定",
            )
    if (
        payload.decision_stage == "pre_review"
        and task.manual_review_requested
        and not payload.bypass_expert_gate
    ):
        raise HTTPException(status_code=409, detail="专家复核门禁仍在生效")
    differs = (
        payload.decision_stage == "pre_review"
        and submission.internal_candidate_decision is not None
        and payload.final_decision != submission.internal_candidate_decision
    )
    if (differs or payload.bypass_expert_gate) and not (
        payload.rationale or ""
    ).strip():
        raise HTTPException(status_code=400, detail="偏离建议或绕过门禁时必须填写理由")
    decision = EditorialDecision(
        submission_id=submission.id,
        version=(latest.version + 1) if latest else 1,
        decision_stage=payload.decision_stage,
        suggested_decision=(
            submission.internal_candidate_decision
            if payload.decision_stage == "pre_review"
            and submission.recommendation_state == "ready"
            else None
        ),
        final_decision=payload.final_decision,
        recommendation_state=submission.recommendation_state,
        rationale=payload.rationale,
        bypassed_expert_gate=payload.bypass_expert_gate,
        actor_id=current_user.id,
        is_locked=True,
        reopened_from_id=latest.id if latest else None,
    )
    submission.status = (
        "sent_for_external_review"
        if payload.decision_stage == "pre_review"
        and payload.final_decision
        in {"send_external_review", "priority_external_review"}
        else "completed"
    )
    submission.retention_due_at = (
        utc_now() + timedelta(days=settings.retention_manuscript_days)
        if submission.status == "completed"
        else None
    )
    db.add(decision)
    db.add(submission)
    db.commit()
    db.refresh(decision)
    record_audit_log(
        db,
        actor_id=current_user.id,
        object_type="editorial_submission",
        object_id=submission.id,
        action=(
            "submit_decision_bypass_expert_gate"
            if payload.bypass_expert_gate
            else "submit_decision"
        ),
        result=payload.final_decision,
        details={
            "version": decision.version,
            "stage": payload.decision_stage,
            "rationale_provided": bool((payload.rationale or "").strip()),
        },
    )
    generate_editorial_report(db, submission.id)
    return EditorialDecisionResponse.model_validate(decision)


@router.get("/submissions/{submission_id}/report")
def get_editorial_report(
    submission_id: str,
    format: str = "json",
    current_user: User = Depends(require_roles("editor", "admin")),
    db: Session = Depends(get_db),
):
    submission = require_submission_access(db, current_user, submission_id)
    if format not in {"json", "pdf"}:
        raise HTTPException(status_code=400, detail="报告格式只能是 JSON 或 PDF")
    kind = f"report_{format}"
    document = (
        db.query(EditorialDocument)
        .filter(
            EditorialDocument.submission_id == submission.id,
            EditorialDocument.kind == kind,
        )
        .order_by(EditorialDocument.version.desc())
        .first()
    )
    if document is None:
        raise HTTPException(status_code=404, detail="尚未生成编辑预审报告")
    content = Path(document.file_path).read_bytes()
    record_audit_log(
        db,
        actor_id=current_user.id,
        object_type="editorial_report",
        object_id=document.id,
        action="access_editorial_report",
        result="allowed",
        details={
            "submission_id": submission.id,
            "format": format,
            "version": document.version,
        },
    )
    if format == "json":
        return JSONResponse(content=json.loads(content))
    return Response(content=content, media_type="application/pdf")
