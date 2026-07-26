from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy.orm import Session

from src.core.config import settings
from src.core.email import send_editorial_event_email
from src.core.time import utc_now
from src.editorial.ai_anonymization import (
    AIAnonymizationOutcome,
    load_anonymization_config,
    run_ai_anonymization,
)
from src.editorial.anonymization import create_anonymized_artifacts
from src.editorial.decision import band_for_score, build_recommendation
from src.editorial.fit import evaluate_journal_fit
from src.editorial.formal_check import evaluate_formal_completeness
from src.editorial.opinions import generate_editorial_opinions
from src.editorial.policy import EditorialPolicy, resolve_submission_policy
from src.editorial.presentation import build_six_dimension_summary
from src.editorial.position import resolve_position_providers, run_position_assessment
from src.editorial.reporting import generate_editorial_report
from src.evaluation.orchestrator import run_evaluation_pipeline
from src.evaluation.precheck import PrecheckResult, run_precheck
from src.evaluation.progress import plan_evaluation_work, set_work_status
from src.evaluation.providers.factory import create_providers
from src.ingestion.preprocessor import process_file
from src.knowledge.loader import load_framework
from src.knowledge.registry import resolve_framework_path
from src.models.editorial import (
    EditorialDocument,
    EditorialOpinion,
    EditorialSubmission,
    EditorialUnit,
    Journal,
    Notification,
    PositionAssessment,
)
from src.models.evaluation import DimensionScore, EvaluationTask
from src.models.paper import Paper
from src.models.reliability import ReliabilityResult
from src.models.user import User


def _final_bands(
    db: Session,
    task: EvaluationTask,
    policy: EditorialPolicy,
) -> tuple[dict[str, str], dict[str, float]]:
    rows = (
        db.query(ReliabilityResult)
        .filter(
            ReliabilityResult.task_id == task.id,
            ReliabilityResult.round_number == task.final_round,
        )
        .all()
    )
    means = {row.dimension_key: row.mean_score for row in rows}
    structured_rows = (
        db.query(DimensionScore)
        .filter(
            DimensionScore.task_id == task.id,
            DimensionScore.round_number == task.final_round,
        )
        .all()
    )
    per_dimension: dict[str, list[str]] = {}
    for row in structured_rows:
        payload = row.structured_payload or {}
        band = payload.get("band") or payload.get("revised_band")
        if band:
            per_dimension.setdefault(row.dimension_key, []).append(str(band))

    bands: dict[str, str] = {}
    for key, mean in means.items():
        model_bands = per_dimension.get(key, [])
        if model_bands and len(set(model_bands)) == 1:
            bands[key] = model_bands[0]
        else:
            bands[key] = band_for_score(mean, policy)
    return bands, means


def _notify_responsible(
    db: Session, submission: EditorialSubmission, event_type: str
) -> None:
    if submission.responsible_editor_id is None:
        return
    db.add(
        Notification(
            user_id=submission.responsible_editor_id,
            event_type=event_type,
            object_type="editorial_submission",
            object_id=submission.id,
            payload={"submission_id": submission.id},
        )
    )
    user = db.get(User, submission.responsible_editor_id)
    if user is not None:
        send_editorial_event_email(
            db=db,
            recipient_email=user.email,
            submission_id=submission.id,
            event_type=event_type,
        )


async def run_editorial_pipeline(
    submission_id: str,
    db: Session,
    *,
    provider_factory=create_providers,
) -> dict:
    """运行编辑预审纵切，所有暂停节点均保留原始结果后返回。"""

    submission = db.get(EditorialSubmission, submission_id)
    if submission is None:
        raise ValueError(f"EditorialSubmission {submission_id} not found")
    paper = db.get(Paper, submission.paper_id)
    task = db.get(EvaluationTask, submission.evaluation_task_id)
    unit = db.get(EditorialUnit, submission.unit_id)
    journal = db.get(Journal, unit.journal_id) if unit else None
    if paper is None or task is None or unit is None or not paper.file_path:
        raise ValueError("编辑投稿所需数据不完整")

    policy = resolve_submission_policy(db, submission)
    provider_names = json.loads(task.provider_names or "[]")
    providers = provider_factory(provider_names)
    if not providers:
        raise ValueError("未配置评价模型")
    framework = load_framework(task.framework_path or resolve_framework_path())
    plan_evaluation_work(
        db,
        task,
        dimension_keys=[dimension.key for dimension in framework.dimensions],
        provider_names=[provider.model_name for provider in providers],
        include_cross_review=task.cross_review_enabled,
        include_signal_check=framework.autonomous_knowledge_signals is not None,
        include_editorial=True,
    )

    try:
        document = (
            db.query(EditorialDocument)
            .filter(
                EditorialDocument.submission_id == submission.id,
                EditorialDocument.kind == "anonymized",
                EditorialDocument.version == 1,
            )
            .first()
        )
        view_document = (
            db.query(EditorialDocument)
            .filter(
                EditorialDocument.submission_id == submission.id,
                EditorialDocument.kind == "anonymized_view",
                EditorialDocument.version == 1,
            )
            .first()
        )
        if document is None:
            set_work_status(db, task.id, "anonymization", "running")
            submission.status = "anonymizing"
            db.commit()
            path, view_path, result, digest, view_digest = create_anonymized_artifacts(
                paper.file_path,
                submission.id,
                version=1,
            )
            documents = [
                EditorialDocument(
                    submission_id=submission.id,
                    kind="anonymized",
                    version=1,
                    file_path=str(path),
                    sha256=digest,
                ),
                EditorialDocument(
                    submission_id=submission.id,
                    kind="anonymized_view",
                    version=1,
                    file_path=str(view_path),
                    sha256=view_digest,
                ),
            ]
            document = documents[0]
            view_document = documents[1]
            submission.anonymization_result = {
                "policy_version": "anonymous-manuscript-v1",
                "document_version": 1,
                "redaction_counts": result.redaction_counts,
                "remaining_markers": result.remaining_markers,
                "requires_confirmation": result.requires_confirmation,
                "risk_flags": result.risk_flags or [],
                "omitted_content_types": result.omitted_content_types or [],
                "human_confirmed": False,
            }
            submission.anonymization_status = "needs_confirmation"
            task.input_file_path = str(path)
            db.add_all(documents)
            db.add(task)
            db.add(submission)
            db.commit()
        anonymization_result = dict(submission.anonymization_result or {})
        ai_result = dict(anonymization_result.get("ai_anonymization") or {})
        if (
            settings.editorial_ai_anonymization_enabled
            and not ai_result.get("attempted")
            and document is not None
            and view_document is not None
        ):
            anonymization_model = "glm-5.2"
            try:
                ai_config = load_anonymization_config()
                anonymization_model = str(ai_config["model_name"])
                anonymization_providers = provider_factory([anonymization_model])
                if not anonymization_providers:
                    raise ValueError("未配置匿名检测模型")
                outcome = await run_ai_anonymization(
                    provider=anonymization_providers[0],
                    task_id=task.id,
                    db=db,
                    text_path=Path(document.file_path),
                    view_path=Path(view_document.file_path),
                    config=ai_config,
                )
            except Exception as exc:
                outcome = AIAnonymizationOutcome(
                    model_name=anonymization_model,
                    status="failed",
                    applied_count=0,
                    requires_manual_review=True,
                    uncertainty_reasons=[
                        f"模型身份检测未启动，已安全转为人工确认：{exc}"
                    ],
                    summary="模型辅助匿名未完成",
                    failure_detail=str(exc),
                )
            if outcome.text_sha256:
                document.sha256 = outcome.text_sha256
            if outcome.view_sha256:
                view_document.sha256 = outcome.view_sha256
            redaction_counts = dict(anonymization_result.get("redaction_counts") or {})
            redaction_counts["model_identity"] = outcome.applied_count
            risk_flags = list(anonymization_result.get("risk_flags") or [])
            if outcome.status == "completed":
                risk_flags = [
                    flag
                    for flag in risk_flags
                    if not flag.startswith("未检测到可自动隐去的身份信息")
                ]
            if outcome.requires_manual_review:
                for reason in outcome.uncertainty_reasons:
                    if reason not in risk_flags:
                        risk_flags.append(reason)
                notice = (
                    f"{outcome.model_name} 已完成初步身份检测，但存在不确定项，"
                    "流程已暂停并等待编辑核对。"
                )
            else:
                notice = (
                    f"{outcome.model_name} 已自动检测并处理匿名信息，共精确隐去 "
                    f"{outcome.applied_count} 处；流程已继续，请编辑知悉并抽查。"
                )
                submission.anonymization_status = "confirmed"
                db.add(
                    Notification(
                        user_id=submission.responsible_editor_id
                        or submission.created_by,
                        event_type="anonymization_auto_processed",
                        object_type="editorial_submission",
                        object_id=submission.id,
                        payload={
                            "submission_id": submission.id,
                            "model_name": outcome.model_name,
                            "applied_count": outcome.applied_count,
                        },
                    )
                )
            anonymization_result.update(
                {
                    "redaction_counts": redaction_counts,
                    "risk_flags": risk_flags,
                    "requires_confirmation": outcome.requires_manual_review,
                    "auto_confirmed": not outcome.requires_manual_review,
                    "confirmed_by_model": (
                        outcome.model_name
                        if not outcome.requires_manual_review
                        else None
                    ),
                    "confirmed_at": (
                        utc_now().isoformat()
                        if not outcome.requires_manual_review
                        else None
                    ),
                    "notice": notice,
                    "ai_anonymization": {
                        "attempted": True,
                        "model_name": outcome.model_name,
                        "status": outcome.status,
                        "applied_count": outcome.applied_count,
                        "requires_manual_review": outcome.requires_manual_review,
                        "uncertainty_reasons": outcome.uncertainty_reasons,
                        "summary": outcome.summary,
                        "failure_detail": outcome.failure_detail,
                    },
                }
            )
            submission.anonymization_result = anonymization_result
            db.add_all([document, view_document, submission])
            db.commit()
        set_work_status(db, task.id, "anonymization", "completed")
        if submission.anonymization_status != "confirmed":
            submission.status = "awaiting_anonymization_confirmation"
            submission.recommendation_state = "withheld"
            db.commit()
            return {"status": submission.status}

        anonymized_text = Path(document.file_path).read_text(encoding="utf-8")
        if submission.formal_check_result is None:
            set_work_status(db, task.id, "formal_check", "running")
            submission.status = "formal_check"
            submission.formal_check_result = evaluate_formal_completeness(
                anonymized_text
            )
            submission.formal_check_status = submission.formal_check_result["status"]
            db.add(submission)
            db.commit()
        set_work_status(db, task.id, "formal_check", "completed")
        if (
            submission.formal_check_status == "boundary"
            and not submission.formal_check_override_reason
        ):
            submission.status = "awaiting_formal_check_confirmation"
            submission.recommendation_state = "withheld"
            db.commit()
            return {"status": submission.status}

        if paper.precheck_result:
            precheck = PrecheckResult(**paper.precheck_result)
        else:
            set_work_status(db, task.id, "precheck", "running")
            submission.status = "prechecking"
            db.commit()
            processed = process_file(document.file_path)
            try:
                precheck = await run_precheck(
                    providers[0], framework, processed, task.id, db
                )
            except Exception as exc:
                set_work_status(
                    db,
                    task.id,
                    "precheck",
                    "failed",
                    failure_detail=str(exc),
                    commit=False,
                )
                task.status = "failed"
                task.failure_stage = "precheck"
                task.failure_detail = str(exc)
                db.add(task)
                db.commit()
                raise
            paper.precheck_status = precheck.status
            paper.precheck_result = precheck.model_dump()
            db.add(paper)
            db.commit()
        set_work_status(db, task.id, "precheck", "completed")
        if precheck.status == "reject" and not submission.precheck_override_reason:
            submission.status = "awaiting_precheck_confirmation"
            submission.recommendation_state = "withheld"
            db.commit()
            return {"status": submission.status}

        if submission.fit_result is None:
            set_work_status(db, task.id, "journal_fit", "running")
            submission.status = "journal_fit_check"
            db.commit()
            fit = await evaluate_journal_fit(
                db,
                task_id=task.id,
                provider=providers[0],
                policy=policy,
                anonymized_text=anonymized_text,
                journal_name=journal.name if journal else unit.name,
                unit_name=unit.name,
            )
            submission.fit_status = fit["status"]
            submission.fit_result = fit
            db.commit()
        set_work_status(db, task.id, "journal_fit", "completed")
        if (
            submission.fit_status in {"boundary", "reject"}
            and not submission.fit_override_reason
        ):
            submission.status = "awaiting_fit_confirmation"
            submission.recommendation_state = "withheld"
            db.commit()
            return {"status": submission.status}

        if (
            task.status != "completed"
            or not db.query(DimensionScore)
            .filter_by(task_id=task.id, round_number=2)
            .first()
        ):
            submission.status = "evaluating"
            db.commit()
            await run_evaluation_pipeline(
                task.id,
                db,
                provider_factory=lambda _: providers,
                precheck_result=precheck,
                force_continue_after_precheck=bool(submission.precheck_override_reason),
            )

        position = (
            db.query(PositionAssessment)
            .filter(
                PositionAssessment.submission_id == submission.id,
                PositionAssessment.status == "completed",
            )
            .order_by(PositionAssessment.version.desc())
            .first()
        )
        if position is None:
            position_providers = resolve_position_providers(
                providers,
                provider_factory,
            )
            for slot in (1, 2):
                set_work_status(
                    db,
                    task.id,
                    f"position_r1:model-{slot}",
                    "running",
                    commit=False,
                )
            db.commit()
            position = await run_position_assessment(
                db,
                submission_id=submission.id,
                task_id=task.id,
                providers=position_providers,
                title=submission.title or paper.title or "",
                journal_name=journal.name if journal else "",
                anonymized_text=anonymized_text,
            )
        for slot in (1, 2):
            set_work_status(
                db,
                task.id,
                f"position_r1:model-{slot}",
                "completed",
                commit=False,
            )
        position_r2_status = (
            "skipped"
            if (position.result_data or {}).get("round2_policy", {}).get("mode")
            == "skip"
            else "completed"
        )
        for slot in (1, 2):
            set_work_status(
                db,
                task.id,
                f"position_r2:model-{slot}",
                position_r2_status,
                commit=False,
            )
        db.commit()

        bands, means = _final_bands(db, task, policy)
        final_scores = (
            db.query(DimensionScore)
            .filter(
                DimensionScore.task_id == task.id,
                DimensionScore.round_number == task.final_round,
            )
            .all()
        )
        final_reliability = (
            db.query(ReliabilityResult)
            .filter(
                ReliabilityResult.task_id == task.id,
                ReliabilityResult.round_number == task.final_round,
            )
            .all()
        )
        evaluation_context = {
            "six_dimension_bands": bands,
            "six_dimension_means": means,
            "four_model_summary": build_six_dimension_summary(
                final_scores,
                final_reliability,
                policy,
                provider_names,
            ),
            "ccb": paper.aggregate_result,
            "position_assessment": position.result_data,
        }
        has_synthesis = (
            db.query(EditorialOpinion)
            .filter(
                EditorialOpinion.submission_id == submission.id,
                EditorialOpinion.opinion_type == "ai_synthesis",
            )
            .first()
        )
        if has_synthesis is None:
            set_work_status(db, task.id, "opinion-synthesis", "running")
            submission.status = "generating_opinions"
            db.commit()
            await generate_editorial_opinions(
                db,
                submission_id=submission.id,
                task_id=task.id,
                providers=providers,
                policy=policy,
                anonymized_text=anonymized_text,
                evaluation_context=evaluation_context,
            )
        set_work_status(db, task.id, "opinion-synthesis", "completed")

        position_review = bool(
            (position.result_data or {}).get("final", {}).get("review_required")
        )
        if position_review:
            task.manual_review_requested = True
            db.add(task)
        recommendation = build_recommendation(
            bands,
            policy,
            rollout_state=unit.rollout_state,
            requires_expert_review=task.manual_review_requested,
        )
        submission.internal_candidate_decision = recommendation.candidate_decision
        submission.recommendation_state = recommendation.state
        submission.status = (
            "expert_review" if task.manual_review_requested else "awaiting_editor"
        )
        _notify_responsible(db, submission, "editorial_review_ready")
        db.add(submission)
        db.commit()
        if submission.current_report_version == 0:
            set_work_status(db, task.id, "report", "running")
            generate_editorial_report(db, submission.id)
            set_work_status(db, task.id, "report", "completed")
        return {
            "status": submission.status,
            "recommendation_state": recommendation.state,
            "withheld_reasons": recommendation.withheld_reasons,
        }
    except Exception:
        submission.status = "recovering"
        submission.recommendation_state = "withheld"
        _notify_responsible(db, submission, "editorial_review_failed")
        db.add(submission)
        db.commit()
        raise
