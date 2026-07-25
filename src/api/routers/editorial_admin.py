from __future__ import annotations

import inspect
import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.api.auth.dependencies import require_roles
from src.api.schemas.editorial import (
    EditorialUnitCreateRequest,
    EditorialUnitListResponse,
    EditorialUnitResponse,
    JournalCreateRequest,
    MembershipCreateRequest,
    ReopenDecisionRequest,
    RolloutStateRequest,
    ValidationRunCreateRequest,
)
from src.core.audit import record_audit_log
from src.core.config import settings
from src.core.database import get_db
from src.core.time import utc_now
from src.editorial.bootstrap import ensure_initial_editorial_units
from src.editorial.policy import deployed_policy_keys, load_editorial_policy
from src.evaluation.cross_review import CrossReviewService
from src.knowledge.registry import load_model_set
from src.models.editorial import (
    EditorialDecision,
    EditorialDocument,
    EditorialSubmission,
    EditorialUnit,
    EditorialUnitMembership,
    Journal,
    ValidationRun,
)
from src.models.evaluation import EvaluationTask
from src.models.user import User

router = APIRouter()


def _validation_response(row: ValidationRun) -> dict:
    return {
        "id": row.id,
        "unit_id": row.unit_id,
        "validation_type": row.validation_type,
        "framework_version": row.framework_version,
        "model_set_version": row.model_set_version,
        "sample_manifest_sha256": row.sample_manifest_sha256,
        "sample_count": row.sample_count,
        "metrics": row.metrics,
        "status": row.status,
        "signed_by": row.signed_by,
        "signed_at": row.signed_at,
        "created_at": row.created_at,
    }


async def _dispatch_evaluation(request: Request, db: Session, task_id: str) -> None:
    runner = getattr(request.app.state, "pipeline_runner", None)
    if runner is not None:
        result = runner(task_id, db)
        if inspect.isawaitable(result):
            await result
        return
    dispatcher = getattr(request.app.state, "task_dispatcher", None)
    if dispatcher is None:
        raise RuntimeError("未配置评价任务调度器")
    dispatcher(task_id)


def _response(db: Session, unit: EditorialUnit) -> EditorialUnitResponse:
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
    )


@router.get("/policies")
def list_policies(
    _: User = Depends(require_roles("admin")),
) -> dict:
    return {"items": deployed_policy_keys()}


@router.get("/model-sets")
def list_model_sets(
    _: User = Depends(require_roles("admin")),
) -> dict:
    """列出生产与候选四模型集合。"""

    def public_model_set(name: str) -> dict:
        model_set = load_model_set(name)
        model_set.pop("legacy_model_groups", None)
        return model_set

    return {
        "items": [
            public_model_set("six-dimension-v1"),
            public_model_set("six-dimension-v2-candidate"),
        ]
    }


@router.get("/validation-runs")
def list_validation_runs(
    unit_id: str | None = None,
    _: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
) -> dict:
    query = db.query(ValidationRun)
    if unit_id:
        query = query.filter(ValidationRun.unit_id == unit_id)
    rows = query.order_by(ValidationRun.created_at.desc()).limit(100).all()
    return {"items": [_validation_response(row) for row in rows]}


@router.post("/validation-runs", status_code=status.HTTP_201_CREATED)
def create_validation_run(
    payload: ValidationRunCreateRequest,
    current_user: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
) -> dict:
    if payload.unit_id and db.get(EditorialUnit, payload.unit_id) is None:
        raise HTTPException(status_code=404, detail="未找到编辑单元")
    row = ValidationRun(**payload.model_dump(), status="draft")
    db.add(row)
    db.commit()
    db.refresh(row)
    record_audit_log(
        db,
        actor_id=current_user.id,
        object_type="validation_run",
        object_id=row.id,
        action="create_validation_run",
        result="draft",
        details={
            "validation_type": row.validation_type,
            "sample_count": row.sample_count,
            "sample_manifest_sha256": row.sample_manifest_sha256,
        },
    )
    return _validation_response(row)


@router.post("/validation-runs/{run_id}/sign")
def sign_validation_run(
    run_id: str,
    current_user: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
) -> dict:
    row = db.get(ValidationRun, run_id)
    if row is None:
        raise HTTPException(status_code=404, detail="未找到验证记录")
    if row.status == "signed":
        return _validation_response(row)
    row.status = "signed"
    row.signed_by = current_user.id
    row.signed_at = utc_now()
    db.commit()
    record_audit_log(
        db,
        actor_id=current_user.id,
        object_type="validation_run",
        object_id=row.id,
        action="sign_validation_run",
        result="signed",
    )
    return _validation_response(row)


@router.post("/submissions/{submission_id}/candidate-run", status_code=202)
async def start_candidate_run(
    submission_id: str,
    request: Request,
    current_user: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
) -> dict:
    """为同一匿名稿创建不覆盖生产结果的新版模型并行任务。"""

    submission = db.get(EditorialSubmission, submission_id)
    if submission is None or submission.evaluation_task_id is None:
        raise HTTPException(status_code=404, detail="未找到投稿或生产评价任务")
    baseline = db.get(EvaluationTask, submission.evaluation_task_id)
    if baseline is None:
        raise HTTPException(status_code=404, detail="未找到生产评价任务")
    anonymous = (
        db.query(EditorialDocument)
        .filter(
            EditorialDocument.submission_id == submission.id,
            EditorialDocument.kind == "anonymized",
            EditorialDocument.file_path == baseline.input_file_path,
        )
        .first()
    )
    if anonymous is None:
        raise HTTPException(
            status_code=409,
            detail="生产任务绑定的匿名稿不存在，不能创建可比候选任务",
        )

    comparison_group_id = baseline.comparison_group_id or str(uuid.uuid4())
    existing = (
        db.query(EvaluationTask)
        .filter(
            EvaluationTask.comparison_group_id == comparison_group_id,
            EvaluationTask.run_role == "candidate",
            EvaluationTask.model_set_version == "six-dimension-v2-candidate",
        )
        .first()
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail="该稿件已经存在候选模型任务")

    model_set = load_model_set("six-dimension-v2-candidate")
    CrossReviewService.for_model_set(model_set["name"]).validate_provider_names(
        model_set["provider_names"]
    )
    baseline.comparison_group_id = comparison_group_id
    baseline.run_role = "baseline"
    candidate = EvaluationTask(
        paper_id=baseline.paper_id,
        framework_id=baseline.framework_id,
        framework_path=baseline.framework_path,
        input_file_path=anonymous.file_path,
        provider_names=json.dumps(model_set["provider_names"], ensure_ascii=False),
        model_set_version=model_set["name"],
        review_protocol_version=model_set["review_protocol"],
        run_role="candidate",
        comparison_group_id=comparison_group_id,
        status="pending",
        cross_review_enabled=True,
        final_round=1,
    )
    db.add(baseline)
    db.add(candidate)
    db.commit()
    db.refresh(candidate)
    record_audit_log(
        db,
        actor_id=current_user.id,
        object_type="evaluation_task",
        object_id=candidate.id,
        action="start_candidate_model_run",
        result="queued",
        details={
            "submission_id": submission.id,
            "baseline_task_id": baseline.id,
            "comparison_group_id": comparison_group_id,
            "model_set_version": model_set["name"],
            "review_protocol_version": model_set["review_protocol"],
        },
    )
    await _dispatch_evaluation(request, db, candidate.id)
    return {
        "task_id": candidate.id,
        "baseline_task_id": baseline.id,
        "comparison_group_id": comparison_group_id,
        "model_set_version": candidate.model_set_version,
        "review_protocol_version": candidate.review_protocol_version,
        "status": candidate.status,
    }


@router.post("/bootstrap", response_model=EditorialUnitListResponse)
def bootstrap_units(
    current_user: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
) -> EditorialUnitListResponse:
    units = ensure_initial_editorial_units(db)
    record_audit_log(
        db,
        actor_id=current_user.id,
        object_type="editorial_configuration",
        object_id="initial-units",
        action="bootstrap_editorial_units",
        result="completed",
        details={"unit_ids": [unit.id for unit in units]},
    )
    return EditorialUnitListResponse(items=[_response(db, unit) for unit in units])


@router.post("/journals", status_code=status.HTTP_201_CREATED)
def create_journal(
    payload: JournalCreateRequest,
    current_user: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
) -> dict:
    journal = Journal(code=payload.code, name=payload.name)
    db.add(journal)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="期刊代码已经存在") from exc
    db.refresh(journal)
    record_audit_log(
        db,
        actor_id=current_user.id,
        object_type="journal",
        object_id=journal.id,
        action="create_journal",
        result="created",
    )
    return {"id": journal.id, "code": journal.code, "name": journal.name}


@router.post(
    "/units",
    response_model=EditorialUnitResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_unit(
    payload: EditorialUnitCreateRequest,
    current_user: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
) -> EditorialUnitResponse:
    if db.get(Journal, payload.journal_id) is None:
        raise HTTPException(status_code=404, detail="未找到期刊")
    try:
        policy = load_editorial_policy(payload.policy_key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    unit = EditorialUnit(
        journal_id=payload.journal_id,
        code=payload.code,
        name=payload.name,
        policy_key=policy.key,
        policy_version=policy.version,
        rollout_state="shadow",
    )
    db.add(unit)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409, detail="该期刊下的编辑单元代码已经存在"
        ) from exc
    db.refresh(unit)
    record_audit_log(
        db,
        actor_id=current_user.id,
        object_type="editorial_unit",
        object_id=unit.id,
        action="create_editorial_unit",
        result="shadow",
    )
    return _response(db, unit)


@router.post("/units/{unit_id}/members", status_code=status.HTTP_201_CREATED)
def add_member(
    unit_id: str,
    payload: MembershipCreateRequest,
    current_user: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
) -> dict:
    if db.get(EditorialUnit, unit_id) is None or db.get(User, payload.user_id) is None:
        raise HTTPException(status_code=404)
    membership = (
        db.query(EditorialUnitMembership)
        .filter(
            EditorialUnitMembership.unit_id == unit_id,
            EditorialUnitMembership.user_id == payload.user_id,
        )
        .first()
    )
    if membership is None:
        membership = EditorialUnitMembership(
            unit_id=unit_id,
            user_id=payload.user_id,
            membership_role=payload.membership_role,
            is_active=True,
        )
    else:
        membership.membership_role = payload.membership_role
        membership.is_active = True
    db.add(membership)
    db.commit()
    db.refresh(membership)
    record_audit_log(
        db,
        actor_id=current_user.id,
        object_type="editorial_unit",
        object_id=unit_id,
        action="upsert_editorial_member",
        result="active",
        details={"user_id": payload.user_id, "role": payload.membership_role},
    )
    return {"id": membership.id, "unit_id": unit_id, "user_id": payload.user_id}


@router.post("/units/{unit_id}/rollout", response_model=EditorialUnitResponse)
def set_rollout_state(
    unit_id: str,
    payload: RolloutStateRequest,
    current_user: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
) -> EditorialUnitResponse:
    unit = db.get(EditorialUnit, unit_id)
    if unit is None:
        raise HTTPException(status_code=404)
    validation_run = (
        db.get(ValidationRun, payload.validation_run_id)
        if payload.validation_run_id
        else None
    )
    if payload.rollout_state == "active" and (
        not payload.editor_signoff
        or (
            validation_run is None
            and (settings.app_env == "production" or not payload.validation_summary)
        )
    ):
        raise HTTPException(
            status_code=400,
            detail="正式启用需要已签字验证记录和编辑确认",
        )
    if validation_run is not None and (
        validation_run.status != "signed"
        or validation_run.unit_id not in (None, unit.id)
    ):
        raise HTTPException(
            status_code=400,
            detail="验证记录未签字或不属于当前编辑单元",
        )
    previous = unit.rollout_state
    unit.rollout_state = payload.rollout_state
    db.commit()
    record_audit_log(
        db,
        actor_id=current_user.id,
        object_type="editorial_unit",
        object_id=unit.id,
        action="set_rollout_state",
        result=unit.rollout_state,
        details={
            "from": previous,
            "reason": payload.reason,
            "validation_summary": payload.validation_summary,
            "validation_run_id": payload.validation_run_id,
            "editor_signoff": payload.editor_signoff,
        },
    )
    return _response(db, unit)


@router.post("/submissions/{submission_id}/reopen")
def reopen_decision(
    submission_id: str,
    payload: ReopenDecisionRequest,
    current_user: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
) -> dict:
    submission = db.get(EditorialSubmission, submission_id)
    if submission is None:
        raise HTTPException(status_code=404)
    latest = (
        db.query(EditorialDecision)
        .filter(EditorialDecision.submission_id == submission.id)
        .order_by(EditorialDecision.version.desc())
        .first()
    )
    if latest is None or not latest.is_locked:
        raise HTTPException(status_code=409, detail="没有可重新打开的已锁定决定")
    latest.is_locked = False
    submission.status = "awaiting_editor"
    db.add(latest)
    db.add(submission)
    db.commit()
    record_audit_log(
        db,
        actor_id=current_user.id,
        object_type="editorial_submission",
        object_id=submission.id,
        action="reopen_decision",
        result="awaiting_editor",
        details={"decision_id": latest.id, "reason": payload.reason},
    )
    return {"submission_id": submission.id, "status": submission.status}
