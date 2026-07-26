from __future__ import annotations

import inspect
import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.api.auth.dependencies import require_roles
from src.api.schemas.editorial import (
    EditorialPolicyRollbackRequest,
    EditorialPolicyVersionRequest,
    EditorialUnitCreateRequest,
    EditorialUnitListResponse,
    EditorialUnitResponse,
    JournalCreateRequest,
    MembershipCreateRequest,
    ReopenDecisionRequest,
    RetentionHoldRequest,
    RolloutStateRequest,
    ValidationRunCreateRequest,
)
from src.core.audit import record_audit_log
from src.core.database import get_db
from src.core.time import utc_now
from src.editorial.bootstrap import ensure_initial_editorial_units
from src.editorial.policy import (
    build_policy_snapshot,
    deployed_policy_keys,
    load_editorial_policy,
    policy_from_version,
    policy_snapshot_digest,
)
from src.evaluation.cross_review import CrossReviewService
from src.knowledge.registry import load_model_set
from src.models.editorial import (
    EditorialDecision,
    EditorialDocument,
    EditorialPolicyVersion,
    EditorialSubmission,
    EditorialUnit,
    EditorialUnitMembership,
    Journal,
    ValidationRun,
)
from src.models.evaluation import EvaluationTask
from src.models.reliability import ReliabilityResult
from src.models.user import User

router = APIRouter()


@router.post("/submissions/{submission_id}/retention-hold")
def set_retention_hold(
    submission_id: str,
    payload: RetentionHoldRequest,
    current_user: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
) -> dict:
    submission = db.get(EditorialSubmission, submission_id)
    if submission is None:
        raise HTTPException(status_code=404, detail="未找到投稿")
    if submission.content_deleted_at is not None:
        raise HTTPException(status_code=409, detail="稿件内容已经按保留策略清理")
    submission.retention_hold_at = utc_now() if payload.enabled else None
    db.add(submission)
    db.commit()
    record_audit_log(
        db,
        actor_id=current_user.id,
        object_type="editorial_submission",
        object_id=submission.id,
        action=(
            "retention_hold_enabled" if payload.enabled else "retention_hold_released"
        ),
        result="success",
        details={"reason": payload.reason},
    )
    return {
        "submission_id": submission.id,
        "retention_hold_at": submission.retention_hold_at,
    }


def _validation_response(row: ValidationRun) -> dict:
    return {
        "id": row.id,
        "unit_id": row.unit_id,
        "validation_type": row.validation_type,
        "framework_version": row.framework_version,
        "model_set_version": row.model_set_version,
        "policy_version_id": row.policy_version_id,
        "sample_manifest_sha256": row.sample_manifest_sha256,
        "sample_count": row.sample_count,
        "metrics": row.metrics,
        "status": row.status,
        "signed_by": row.signed_by,
        "signer_membership_role": row.signer_membership_role,
        "rejection_reason": row.rejection_reason,
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
        trial_policy_version_id=unit.trial_policy_version_id,
        active_policy_version_id=unit.active_policy_version_id,
    )


def _policy_version_response(row: EditorialPolicyVersion) -> dict:
    snapshot = row.snapshot
    if isinstance(snapshot, str):
        snapshot = json.loads(snapshot)
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
    }


@router.get("/policies")
def list_policies(
    _: User = Depends(require_roles("admin")),
) -> dict:
    return {"items": deployed_policy_keys()}


@router.get("/units/{unit_id}/policy-versions")
def list_policy_versions(
    unit_id: str,
    _: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
) -> dict:
    if db.get(EditorialUnit, unit_id) is None:
        raise HTTPException(status_code=404, detail="未找到编辑单元")
    rows = (
        db.query(EditorialPolicyVersion)
        .filter(EditorialPolicyVersion.unit_id == unit_id)
        .order_by(EditorialPolicyVersion.created_at.desc())
        .all()
    )
    return {"items": [_policy_version_response(row) for row in rows]}


def _policy_snapshot_from_request(
    db: Session,
    unit: EditorialUnit,
    payload: EditorialPolicyVersionRequest,
) -> tuple[dict, str | None]:
    based_on = (
        db.get(EditorialPolicyVersion, payload.based_on_id)
        if payload.based_on_id
        else None
    )
    if based_on is not None and based_on.unit_id != unit.id:
        raise HTTPException(status_code=400, detail="基础策略版本不属于当前编辑单元")
    if payload.based_on_id and based_on is None:
        raise HTTPException(status_code=404, detail="未找到基础策略版本")
    try:
        load_model_set(payload.model_set_version)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    journal = db.get(Journal, unit.journal_id)
    profile = {
        "journal_name": journal.name if journal else unit.name,
        "unit_name": unit.name,
        **payload.profile.model_dump(),
    }
    snapshot = build_policy_snapshot(
        policy_key=unit.policy_key,
        version=payload.version,
        profile=profile,
        model_set_version=payload.model_set_version,
    )
    return snapshot, based_on.id if based_on else None


@router.post(
    "/units/{unit_id}/policy-versions",
    status_code=status.HTTP_201_CREATED,
)
def create_policy_version(
    unit_id: str,
    payload: EditorialPolicyVersionRequest,
    current_user: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
) -> dict:
    unit = db.get(EditorialUnit, unit_id)
    if unit is None:
        raise HTTPException(status_code=404, detail="未找到编辑单元")
    snapshot, based_on_id = _policy_snapshot_from_request(db, unit, payload)
    row = EditorialPolicyVersion(
        unit_id=unit.id,
        policy_key=unit.policy_key,
        version=payload.version,
        status="draft",
        snapshot=snapshot,
        content_sha256=policy_snapshot_digest(snapshot),
        based_on_id=based_on_id,
        created_by=current_user.id,
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="策略版本号已经存在") from exc
    db.refresh(row)
    record_audit_log(
        db,
        actor_id=current_user.id,
        object_type="editorial_policy_version",
        object_id=row.id,
        action="create_policy_draft",
        result="draft",
        details={"unit_id": unit.id, "version": row.version},
    )
    return _policy_version_response(row)


@router.put("/policy-versions/{version_id}")
def update_policy_version(
    version_id: str,
    payload: EditorialPolicyVersionRequest,
    current_user: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
) -> dict:
    row = db.get(EditorialPolicyVersion, version_id)
    if row is None:
        raise HTTPException(status_code=404, detail="未找到策略版本")
    if row.status != "draft":
        raise HTTPException(status_code=409, detail="试运行后策略不可直接修改")
    unit = db.get(EditorialUnit, row.unit_id)
    if unit is None:
        raise HTTPException(status_code=404, detail="未找到编辑单元")
    snapshot, based_on_id = _policy_snapshot_from_request(db, unit, payload)
    row.version = payload.version
    row.snapshot = snapshot
    row.content_sha256 = policy_snapshot_digest(snapshot)
    row.based_on_id = based_on_id
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="策略版本号已经存在") from exc
    record_audit_log(
        db,
        actor_id=current_user.id,
        object_type="editorial_policy_version",
        object_id=row.id,
        action="update_policy_draft",
        result="draft",
    )
    return _policy_version_response(row)


@router.post("/policy-versions/{version_id}/trial")
def freeze_policy_for_trial(
    version_id: str,
    current_user: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
) -> dict:
    row = db.get(EditorialPolicyVersion, version_id)
    if row is None:
        raise HTTPException(status_code=404, detail="未找到策略版本")
    if row.status != "draft":
        raise HTTPException(status_code=409, detail="只有草稿可以进入试运行")
    unit = db.get(EditorialUnit, row.unit_id)
    if unit is None:
        raise HTTPException(status_code=404, detail="未找到编辑单元")
    policy_from_version(row)
    if unit.trial_policy_version_id:
        previous = db.get(EditorialPolicyVersion, unit.trial_policy_version_id)
        if previous is not None and previous.status == "trial":
            previous.status = "retired"
            db.add(previous)
    row.status = "trial"
    row.frozen_at = utc_now()
    unit.trial_policy_version_id = row.id
    if unit.rollout_state != "active":
        unit.policy_key = row.policy_key
        unit.policy_version = row.version
    db.add_all([row, unit])
    db.commit()
    record_audit_log(
        db,
        actor_id=current_user.id,
        object_type="editorial_policy_version",
        object_id=row.id,
        action="freeze_policy_for_trial",
        result="trial",
        details={"unit_id": unit.id, "content_sha256": row.content_sha256},
    )
    return _policy_version_response(row)


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
    if payload.policy_version_id:
        policy_version = db.get(
            EditorialPolicyVersion,
            payload.policy_version_id,
        )
        if policy_version is None:
            raise HTTPException(status_code=404, detail="未找到策略版本")
        if payload.unit_id != policy_version.unit_id:
            raise HTTPException(status_code=400, detail="验证记录与策略编辑单元不一致")
        policy = policy_from_version(policy_version)
        if (
            payload.framework_version != policy.framework_version
            or payload.model_set_version != policy.model_set_version
        ):
            raise HTTPException(
                status_code=400,
                detail="验证记录的框架或模型集与策略快照不一致",
            )
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
    del run_id, current_user, db
    raise HTTPException(
        status_code=403,
        detail="验证记录必须由当前编辑单元负责人签署",
    )


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


@router.get("/model-comparisons")
def get_model_comparison(
    submission_id: str = Query(min_length=1),
    _: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
) -> dict:
    submission = db.get(EditorialSubmission, submission_id)
    if submission is None or submission.evaluation_task_id is None:
        raise HTTPException(status_code=404, detail="未找到投稿评价任务")
    baseline = db.get(EvaluationTask, submission.evaluation_task_id)
    if baseline is None or not baseline.comparison_group_id:
        return {"submission_id": submission_id, "items": []}
    tasks = (
        db.query(EvaluationTask)
        .filter(EvaluationTask.comparison_group_id == baseline.comparison_group_id)
        .order_by(EvaluationTask.run_role)
        .all()
    )
    items = []
    score_maps: dict[str, dict[str, float]] = {}
    for task in tasks:
        rows = (
            db.query(ReliabilityResult)
            .filter(
                ReliabilityResult.task_id == task.id,
                ReliabilityResult.round_number == task.final_round,
            )
            .order_by(ReliabilityResult.dimension_key)
            .all()
        )
        metrics = [
            {
                "dimension_key": row.dimension_key,
                "mean_score": row.mean_score,
                "std_score": row.std_score,
                "requires_expert_review": row.std_score > 8,
            }
            for row in rows
        ]
        score_maps[task.run_role] = {row.dimension_key: row.mean_score for row in rows}
        items.append(
            {
                "task_id": task.id,
                "run_role": task.run_role,
                "status": task.status,
                "model_set_version": task.model_set_version,
                "review_protocol_version": task.review_protocol_version,
                "provider_names": json.loads(task.provider_names or "[]"),
                "final_round": task.final_round,
                "metrics": metrics,
            }
        )
    baseline_scores = score_maps.get("baseline", {})
    candidate_scores = score_maps.get("candidate", {})
    deltas = [
        {
            "dimension_key": key,
            "baseline_score": baseline_scores[key],
            "candidate_score": candidate_scores[key],
            "delta": candidate_scores[key] - baseline_scores[key],
        }
        for key in sorted(baseline_scores.keys() & candidate_scores.keys())
    ]
    return {
        "submission_id": submission_id,
        "comparison_group_id": baseline.comparison_group_id,
        "items": items,
        "deltas": deltas,
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
    db.flush()
    profile = {
        **policy.profile,
        "accepted_scope": [str(policy.profile["fit_focus"])],
        "excluded_scope": [],
        "column_positioning": [],
        "article_types": ["法学研究论文"],
        "target_readers": ["法学研究者与法律实务工作者"],
        "special_notes": "",
    }
    snapshot = build_policy_snapshot(
        policy_key=policy.key,
        version=policy.version,
        profile=profile,
        model_set_version="six-dimension-v2-candidate",
    )
    policy_version = EditorialPolicyVersion(
        unit_id=unit.id,
        policy_key=policy.key,
        version=policy.version,
        status="trial",
        snapshot=snapshot,
        content_sha256=policy_snapshot_digest(snapshot),
        created_by=current_user.id,
        frozen_at=utc_now(),
    )
    db.add(policy_version)
    db.flush()
    unit.trial_policy_version_id = policy_version.id
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
    policy_version_id = payload.policy_version_id or unit.trial_policy_version_id
    policy_version = (
        db.get(EditorialPolicyVersion, policy_version_id) if policy_version_id else None
    )
    validation_run = (
        db.get(ValidationRun, payload.validation_run_id)
        if payload.validation_run_id
        else None
    )
    previous = unit.rollout_state
    if payload.rollout_state == "active":
        if (
            policy_version is None
            or policy_version.unit_id != unit.id
            or policy_version.status != "trial"
        ):
            raise HTTPException(
                status_code=400,
                detail="正式启用需要当前编辑单元的试运行策略版本",
            )
        if (
            validation_run is None
            or validation_run.status != "signed"
            or validation_run.unit_id != unit.id
            or validation_run.policy_version_id != policy_version.id
            or validation_run.signer_membership_role != "unit_admin"
        ):
            raise HTTPException(
                status_code=400,
                detail="正式启用需要单元负责人签署的匹配验证记录",
            )
        signer_membership = (
            db.query(EditorialUnitMembership)
            .filter(
                EditorialUnitMembership.unit_id == unit.id,
                EditorialUnitMembership.user_id == validation_run.signed_by,
                EditorialUnitMembership.membership_role == "unit_admin",
                EditorialUnitMembership.is_active.is_(True),
            )
            .first()
        )
        if signer_membership is None:
            raise HTTPException(status_code=400, detail="签署人已不再是单元负责人")
        if unit.active_policy_version_id:
            old_active = db.get(
                EditorialPolicyVersion,
                unit.active_policy_version_id,
            )
            if old_active is not None and old_active.id != policy_version.id:
                old_active.status = "retired"
                db.add(old_active)
        policy_version.status = "active"
        policy_version.activated_by = current_user.id
        policy_version.activated_at = utc_now()
        unit.active_policy_version_id = policy_version.id
        if unit.trial_policy_version_id == policy_version.id:
            unit.trial_policy_version_id = None
        unit.policy_key = policy_version.policy_key
        unit.policy_version = policy_version.version
        unit.rollout_state = "active"
        db.add(policy_version)
    else:
        if unit.trial_policy_version_id:
            current_trial = db.get(
                EditorialPolicyVersion,
                unit.trial_policy_version_id,
            )
            if current_trial is not None:
                current_trial.status = "retired"
                db.add(current_trial)
        current_active = (
            db.get(EditorialPolicyVersion, unit.active_policy_version_id)
            if unit.active_policy_version_id
            else None
        )
        if current_active is not None:
            current_active.status = "trial"
            unit.trial_policy_version_id = current_active.id
            unit.policy_key = current_active.policy_key
            unit.policy_version = current_active.version
            db.add(current_active)
        unit.active_policy_version_id = None
        unit.rollout_state = "shadow"
    db.add(unit)
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
            "policy_version_id": policy_version_id,
        },
    )
    return _response(db, unit)


@router.post(
    "/units/{unit_id}/policy-rollback",
    response_model=EditorialUnitResponse,
)
def rollback_policy_version(
    unit_id: str,
    payload: EditorialPolicyRollbackRequest,
    current_user: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
) -> EditorialUnitResponse:
    unit = db.get(EditorialUnit, unit_id)
    target = db.get(EditorialPolicyVersion, payload.policy_version_id)
    if unit is None or target is None or target.unit_id != unit_id:
        raise HTTPException(status_code=404, detail="未找到可回滚的策略版本")
    if target.status != "retired" or target.activated_at is None:
        raise HTTPException(status_code=409, detail="只能回滚到曾经正式启用的版本")
    current = (
        db.get(EditorialPolicyVersion, unit.active_policy_version_id)
        if unit.active_policy_version_id
        else None
    )
    if current is not None:
        current.status = "retired"
        db.add(current)
    target.status = "active"
    target.activated_by = current_user.id
    target.activated_at = utc_now()
    unit.active_policy_version_id = target.id
    unit.policy_key = target.policy_key
    unit.policy_version = target.version
    unit.rollout_state = "active"
    db.add_all([target, unit])
    db.commit()
    record_audit_log(
        db,
        actor_id=current_user.id,
        object_type="editorial_policy_version",
        object_id=target.id,
        action="rollback_policy_version",
        result="active",
        details={"unit_id": unit.id, "reason": payload.reason},
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
