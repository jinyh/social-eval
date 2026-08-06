from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from sqlalchemy.orm import Session

from src.api.auth.dependencies import require_roles
from src.api.routers.editorial import create_editorial_submission
from src.api.schemas.submitter import (
    SubmitterJournal,
    SubmitterOpinionResponse,
    SubmitterSubmission,
    WithdrawalRequestCreate,
)
from src.core.audit import record_audit_log
from src.core.database import get_db
from src.core.email import queue_email
from src.editorial.policy import policy_from_version
from src.editorial.presentation import localize_synthesis_payload
from src.models.editorial import (
    EditorialOpinion,
    EditorialPolicyVersion,
    EditorialSubmission,
    EditorialUnit,
    Journal,
    SubmissionAuthorRelease,
    SubmissionWithdrawalRequest,
)
from src.models.user import User

router = APIRouter()


STATUS_LABELS = {
    "queued": "已收稿",
    "anonymizing": "稿件处理中",
    "awaiting_anonymization_confirmation": "等待编辑处理",
    "formal_check": "形式检查中",
    "awaiting_formal_check_confirmation": "等待编辑处理",
    "prechecking": "内容检查中",
    "awaiting_precheck_confirmation": "等待编辑处理",
    "journal_fit_check": "期刊适配检查中",
    "awaiting_fit_confirmation": "等待编辑处理",
    "evaluating": "智能辅助评阅中",
    "generating_opinions": "报告生成中",
    "expert_review": "专业复核中",
    "awaiting_editor": "等待编辑决定",
    "sent_for_external_review": "已送外审",
    "completed": "编辑处理完成",
    "recovering": "处理中断，正在恢复",
    "withdrawn": "已撤稿",
}


def _owned_submission(
    db: Session,
    current_user: User,
    submission_id: str,
) -> EditorialSubmission:
    row = (
        db.query(EditorialSubmission)
        .filter(
            EditorialSubmission.id == submission_id,
            EditorialSubmission.created_by == current_user.id,
        )
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="未找到投稿")
    return row


def _submission_response(
    db: Session,
    row: EditorialSubmission,
) -> SubmitterSubmission:
    unit = db.get(EditorialUnit, row.unit_id)
    journal = db.get(Journal, unit.journal_id) if unit else None
    release = (
        db.query(SubmissionAuthorRelease)
        .filter(SubmissionAuthorRelease.submission_id == row.id)
        .order_by(SubmissionAuthorRelease.released_at.desc())
        .first()
    )
    withdrawal = (
        db.query(SubmissionWithdrawalRequest)
        .filter(SubmissionWithdrawalRequest.submission_id == row.id)
        .order_by(SubmissionWithdrawalRequest.requested_at.desc())
        .first()
    )
    return SubmitterSubmission(
        id=row.id,
        paper_id=row.paper_id,
        unit_id=row.unit_id,
        journal_name=journal.name if journal else "",
        unit_name=unit.name if unit else "",
        title=row.title or "未命名稿件",
        status=row.status,
        status_label=STATUS_LABELS.get(row.status, "处理中"),
        created_at=row.created_at,
        updated_at=row.updated_at,
        report_released=release is not None,
        public_decision=release.public_decision if release else None,
        author_message=release.author_message if release else None,
        withdrawal_status=withdrawal.status if withdrawal else None,
        root_submission_id=row.root_submission_id or row.id,
        resubmission_round=row.resubmission_round,
    )


@router.get("/journals", response_model=list[SubmitterJournal])
def list_journals(
    _: User = Depends(require_roles("submitter")),
    db: Session = Depends(get_db),
) -> list[SubmitterJournal]:
    units = (
        db.query(EditorialUnit)
        .filter(
            EditorialUnit.rollout_state == "active",
            EditorialUnit.is_active.is_(True),
            EditorialUnit.active_policy_version_id.is_not(None),
        )
        .order_by(EditorialUnit.name)
        .all()
    )
    items: list[SubmitterJournal] = []
    for unit in units:
        version = db.get(EditorialPolicyVersion, unit.active_policy_version_id)
        journal = db.get(Journal, unit.journal_id)
        if version is None or version.status != "active" or journal is None:
            continue
        profile = policy_from_version(version).profile
        items.append(
            SubmitterJournal(
                unit_id=unit.id,
                journal_name=journal.name,
                unit_name=unit.name,
                accepted_scope=list(profile.get("accepted_scope", [])),
                column_positioning=list(profile.get("column_positioning", [])),
                article_types=list(profile.get("article_types", [])),
                special_notes=str(profile.get("special_notes", "")),
            )
        )
    return items


@router.post("/submissions", status_code=202)
async def submit_manuscript(
    request: Request,
    unit_id: str = Form(...),
    title: str = Form(..., min_length=2, max_length=500),
    file: UploadFile = File(...),
    previous_submission_id: str | None = Form(None),
    current_user: User = Depends(require_roles("submitter")),
    db: Session = Depends(get_db),
) -> dict:
    unit = (
        db.query(EditorialUnit)
        .filter(
            EditorialUnit.id == unit_id,
            EditorialUnit.rollout_state == "active",
            EditorialUnit.is_active.is_(True),
            EditorialUnit.active_policy_version_id.is_not(None),
        )
        .first()
    )
    if unit is None:
        raise HTTPException(status_code=400, detail="所选期刊暂未开放投稿")
    result = await create_editorial_submission(
        request,
        db,
        unit=unit,
        file=file,
        external_manuscript_id=None,
        current_user=current_user,
        title=title.strip(),
        previous_submission_id=previous_submission_id,
    )
    queue_email(
        db,
        idempotency_key=f"submitter-receipt:{result.submission_id}",
        event_type="submitter_submission_received",
        recipient_email=current_user.email,
        object_type="editorial_submission",
        object_id=result.submission_id,
        template_data={"system_id": result.submission_id},
    )
    return result.model_dump()


@router.get("/submissions", response_model=list[SubmitterSubmission])
def list_submissions(
    current_user: User = Depends(require_roles("submitter")),
    db: Session = Depends(get_db),
) -> list[SubmitterSubmission]:
    rows = (
        db.query(EditorialSubmission)
        .filter(EditorialSubmission.created_by == current_user.id)
        .order_by(
            EditorialSubmission.resubmission_round.desc(),
            EditorialSubmission.created_at.desc(),
        )
        .all()
    )
    # 同一篇论文（按 root_submission_id）只显示最新一轮，"只算1篇"
    seen_roots: set[str] = set()
    deduped: list[EditorialSubmission] = []
    for row in rows:
        root = row.root_submission_id or row.id
        if root in seen_roots:
            continue
        seen_roots.add(root)
        deduped.append(row)
    return [_submission_response(db, row) for row in deduped]


@router.get(
    "/submissions/{submission_id}",
    response_model=SubmitterSubmission,
)
def get_submission(
    submission_id: str,
    current_user: User = Depends(require_roles("submitter")),
    db: Session = Depends(get_db),
) -> SubmitterSubmission:
    return _submission_response(
        db,
        _owned_submission(db, current_user, submission_id),
    )


@router.get(
    "/submissions/{submission_id}/opinion",
    response_model=SubmitterOpinionResponse,
)
def get_submission_opinion(
    submission_id: str,
    current_user: User = Depends(require_roles("submitter")),
    db: Session = Depends(get_db),
) -> SubmitterOpinionResponse:
    """投稿人预审反馈：综合意见 + 修改建议。

    纯预审模式，综合意见生成后即可见，不等编辑发布（release）。
    """

    submission = _owned_submission(db, current_user, submission_id)
    opinion = (
        db.query(EditorialOpinion)
        .filter(
            EditorialOpinion.submission_id == submission.id,
            EditorialOpinion.opinion_type == "ai_synthesis",
        )
        .order_by(EditorialOpinion.version.desc())
        .first()
    )
    if opinion is None:
        return SubmitterOpinionResponse(ready=False)
    content = localize_synthesis_payload(opinion.content)
    return SubmitterOpinionResponse(
        ready=True,
        synthesis=str(content.get("synthesis") or ""),
        modification_suggestions=list(content.get("modification_suggestions") or []),
    )


@router.post("/submissions/{submission_id}/withdrawal-requests", status_code=201)
def request_withdrawal(
    submission_id: str,
    payload: WithdrawalRequestCreate,
    current_user: User = Depends(require_roles("submitter")),
    db: Session = Depends(get_db),
) -> dict:
    submission = _owned_submission(db, current_user, submission_id)
    if submission.status == "withdrawn":
        raise HTTPException(status_code=409, detail="稿件已经撤回")
    pending = (
        db.query(SubmissionWithdrawalRequest)
        .filter(
            SubmissionWithdrawalRequest.submission_id == submission.id,
            SubmissionWithdrawalRequest.status == "pending",
        )
        .first()
    )
    if pending is not None:
        raise HTTPException(status_code=409, detail="已有待处理的撤稿申请")
    row = SubmissionWithdrawalRequest(
        submission_id=submission.id,
        requested_by=current_user.id,
        reason=payload.reason.strip(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    record_audit_log(
        db,
        actor_id=current_user.id,
        object_type="editorial_submission",
        object_id=submission.id,
        action="withdrawal_requested",
        result="pending",
    )
    return {"id": row.id, "status": row.status}
