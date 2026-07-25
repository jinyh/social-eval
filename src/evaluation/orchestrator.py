from __future__ import annotations

import json
import logging

from sqlalchemy.orm import Session

from src.core.state_machine import ensure_valid_task_transition
from src.core.time import utc_now
from src.evaluation.concurrent_evaluator import evaluate_dimension_concurrent
from src.evaluation.cross_review import CrossReviewService
from src.evaluation.precheck import run_precheck
from src.evaluation.precheck import PrecheckResult
from src.evaluation.progress import (
    mark_model_results,
    plan_evaluation_work,
    set_work_status,
)
from src.evaluation.providers.factory import create_providers
from src.evaluation.result_validator import aggregate_result, aggregate_result_to_dict
from src.evaluation.signal_check import (
    aggregate_signal_results,
    check_contradiction_triggers,
    run_signal_check_multi,
    signal_to_dict,
)
from src.ingestion.preprocessor import process_file
from src.knowledge.loader import load_framework
from src.knowledge.registry import resolve_framework_path
from src.models.evaluation import DimensionScore, EvaluationTask
from src.models.evaluation import EvaluationWorkUnit
from src.models.paper import Paper
from src.models.reliability import ReliabilityResult
from src.reliability.calculator import calculate_reliability
from src.reliability.threshold_checker import summarize_reliability
from src.reporting.scoring import calculate_weighted_total
from src.reporting.versioning import generate_reports_for_task
from src.evaluation.schemas import DimensionResult

logger = logging.getLogger(__name__)


def _confidence_level(std_score: float) -> str:
    if std_score <= 5:
        return "high"
    if std_score <= 8:
        return "medium"
    if std_score <= 12:
        return "low"
    return "critical"


def _stored_dimension_results(
    db: Session,
    task_id: str,
    dimension_key: str,
    round_number: int,
    provider_names: list[str],
) -> list[DimensionResult] | None:
    by_model = _stored_dimension_result_map(
        db,
        task_id,
        dimension_key,
        round_number,
        provider_names,
    )
    if not all(name in by_model for name in provider_names):
        return None
    return [by_model[name] for name in provider_names]


def _stored_dimension_result_map(
    db: Session,
    task_id: str,
    dimension_key: str,
    round_number: int,
    provider_names: list[str],
) -> dict[str, DimensionResult]:
    rows = (
        db.query(DimensionScore)
        .filter(
            DimensionScore.task_id == task_id,
            DimensionScore.dimension_key == dimension_key,
            DimensionScore.round_number == round_number,
        )
        .all()
    )
    allowed = set(provider_names)
    results: dict[str, DimensionResult] = {}
    for row in rows:
        if row.model_name not in allowed or row.model_name in results:
            continue
        payload = row.structured_payload or {}
        results[row.model_name] = DimensionResult(
            dimension=dimension_key,
            score=round(row.score),
            evidence_quotes=list(row.evidence_quotes or []),
            analysis=row.analysis,
            band=payload.get("band") or payload.get("revised_band"),
            model_name=row.model_name,
        )
    return results


def _set_model_units_running(
    db: Session,
    task_id: str,
    *,
    prefix: str,
    dimension_key: str,
    provider_names: list[str],
) -> None:
    for name in provider_names:
        set_work_status(
            db,
            task_id,
            f"{prefix}:{dimension_key}:{name}",
            "running",
            commit=False,
        )
    db.commit()


async def run_evaluation_pipeline(
    task_id: str,
    db: Session,
    *,
    provider_factory=create_providers,
    precheck_result: PrecheckResult | None = None,
    force_continue_after_precheck: bool = False,
) -> dict:
    task = db.get(EvaluationTask, task_id)
    if task is None:
        raise ValueError(f"EvaluationTask {task_id} not found")

    paper = db.get(Paper, task.paper_id)
    input_file_path = task.input_file_path or (paper.file_path if paper else None)
    if paper is None or not input_file_path:
        raise ValueError(f"Paper for task {task_id} not found or missing file")

    framework = load_framework(task.framework_path or resolve_framework_path())
    provider_names = json.loads(
        task.provider_names or '["openai","anthropic","deepseek"]'
    )
    providers = provider_factory(provider_names)
    if not providers:
        raise ValueError("No providers configured")
    cross_review = (
        CrossReviewService.for_model_set(
            task.model_set_version,
            review_protocol_name=task.review_protocol_version,
        )
        if task.cross_review_enabled
        else None
    )
    if cross_review is not None:
        cross_review.validate_provider_names(
            [provider.model_name for provider in providers]
        )
    actual_provider_names = [provider.model_name for provider in providers]
    plan_evaluation_work(
        db,
        task,
        dimension_keys=[dimension.key for dimension in framework.dimensions],
        provider_names=actual_provider_names,
        include_cross_review=cross_review is not None,
        include_signal_check=framework.autonomous_knowledge_signals is not None,
        include_editorial=False,
    )

    task.status = "processing"
    task.failure_stage = None
    task.failure_detail = None
    paper.status = "processing"
    db.add(task)
    db.add(paper)
    db.commit()

    try:
        processed_paper = process_file(input_file_path)
        precheck = precheck_result
        if precheck is None:
            set_work_status(db, task.id, "precheck", "running")
            precheck = await run_precheck(
                providers[0],
                framework,
                processed_paper,
                task.id,
                db,
            )
        set_work_status(db, task.id, "precheck", "completed")
        paper.precheck_status = precheck.status
        paper.precheck_result = precheck.model_dump()
        db.add(paper)
        db.commit()

        if precheck.status == "reject" and not force_continue_after_precheck:
            # v0.15 §2.1：reject = 明显不适格 → 不进入六维评分，但必须人工确认
            # 仍需按 aggregate_output_contract 产出报告（review_level=precheck_level）
            agg = aggregate_result(
                dimension_scores={},
                precheck_result=precheck,
                signal_result=None,
                reliability_reports=[],
                framework=framework,
                contradiction_rules=[],
            )
            paper.aggregate_result = aggregate_result_to_dict(agg)
            if agg.review_status == "required":
                task.manual_review_requested = True
            db.add(paper)
            db.add(task)
            db.commit()

            ensure_valid_task_transition(task.status, "completed")
            task.status = "completed"
            paper.status = "completed"
            db.add(task)
            db.add(paper)
            db.commit()
            pending_units = (
                db.query(EvaluationWorkUnit)
                .filter(
                    EvaluationWorkUnit.task_id == task.id,
                    EvaluationWorkUnit.status == "pending",
                    EvaluationWorkUnit.unit_key != "report",
                )
                .all()
            )
            for unit in pending_units:
                unit.status = "skipped"
                unit.completed_at = utc_now()
            db.commit()
            set_work_status(db, task.id, "report", "running")
            generate_reports_for_task(db, task.id)
            set_work_status(db, task.id, "report", "completed")
            return {
                "task_status": task.status,
                "paper_status": paper.status,
                "precheck_status": paper.precheck_status,
                "reliability_summary": None,
                "review_status": agg.review_status,
                "review_level": agg.review_level,
            }

        reliability_reports = []
        dimension_means: dict[str, float] = {}
        per_model_scores: dict[str, dict[str, float]] = {}
        for dimension in framework.dimensions:
            round1_by_model = _stored_dimension_result_map(
                db,
                task.id,
                dimension.key,
                1,
                actual_provider_names,
            )
            missing_names = [
                name for name in actual_provider_names if name not in round1_by_model
            ]
            if missing_names:
                _set_model_units_running(
                    db,
                    task.id,
                    prefix="r1",
                    dimension_key=dimension.key,
                    provider_names=missing_names,
                )
                missing_providers = [
                    provider
                    for provider in providers
                    if provider.model_name in missing_names
                ]
                new_round1_results = await evaluate_dimension_concurrent(
                    missing_providers,
                    dimension,
                    processed_paper,
                    task.id,
                    db,
                )
                for result in new_round1_results:
                    if result.model_name in round1_by_model:
                        continue
                    db.add(
                        DimensionScore(
                            task_id=task.id,
                            dimension_key=dimension.key,
                            model_name=result.model_name,
                            score=result.score,
                            evidence_quotes=result.evidence_quotes,
                            analysis=result.analysis,
                            structured_payload=result.model_dump(),
                            round_number=1,
                        )
                    )
                    round1_by_model[result.model_name] = result
                db.commit()
                mark_model_results(
                    db,
                    task.id,
                    phase="six_dimension_r1",
                    dimension_key=dimension.key,
                    model_names=[result.model_name for result in new_round1_results],
                )

            still_missing = [
                name for name in actual_provider_names if name not in round1_by_model
            ]
            if still_missing:
                waiting_prefix = (
                    "等待四模型第一轮评价齐全；"
                    if cross_review is not None
                    and cross_review.review_mode == "all_peers"
                    else ""
                )
                detail = (
                    waiting_prefix
                    + f"{dimension.name_zh}第一轮缺少有效模型结果："
                    + "、".join(still_missing)
                )
                for name in still_missing:
                    set_work_status(
                        db,
                        task.id,
                        f"r1:{dimension.key}:{name}",
                        "failed",
                        failure_detail=detail,
                        commit=False,
                    )
                db.commit()
                raise ValueError(detail)

            round1_results = [round1_by_model[name] for name in actual_provider_names]

            round1_report = calculate_reliability(
                dimension.key,
                round1_results,
                std_threshold=framework.std_threshold,
            )
            existing_round1_reliability = (
                db.query(ReliabilityResult)
                .filter(
                    ReliabilityResult.task_id == task.id,
                    ReliabilityResult.dimension_key == dimension.key,
                    ReliabilityResult.round_number == 1,
                )
                .first()
            )
            round1_values = {
                "mean_score": round1_report.mean,
                "std_score": round1_report.std,
                "is_high_confidence": round1_report.is_high_confidence,
                "model_scores": round1_report.model_scores,
                "confidence_level": _confidence_level(round1_report.std),
                "requires_evidence_supplement": round1_report.std > 8,
                "divergence_description": (
                    "模型分歧超过专家复核阈值" if round1_report.std > 8 else ""
                ),
            }
            if existing_round1_reliability is None:
                db.add(
                    ReliabilityResult(
                        task_id=task.id,
                        dimension_key=dimension.key,
                        round_number=1,
                        **round1_values,
                    )
                )
            else:
                for key, value in round1_values.items():
                    setattr(existing_round1_reliability, key, value)
                db.add(existing_round1_reliability)
            db.commit()
            mark_model_results(
                db,
                task.id,
                phase="six_dimension_r1",
                dimension_key=dimension.key,
                model_names=[result.model_name for result in round1_results],
            )

            final_results = round1_results
            final_report = round1_report
            if cross_review is not None:
                round2_results = _stored_dimension_results(
                    db,
                    task.id,
                    dimension.key,
                    2,
                    actual_provider_names,
                )
                round2_was_stored = round2_results is not None
                outcomes = []
                if round2_results is None:
                    _set_model_units_running(
                        db,
                        task.id,
                        prefix="r2",
                        dimension_key=dimension.key,
                        provider_names=actual_provider_names,
                    )
                    outcomes = await cross_review.evaluate_dimension(
                        providers,
                        dimension,
                        processed_paper,
                        {result.model_name: result for result in round1_results},
                        task_id=task.id,
                        db=db,
                    )
                    round2_results = [outcome.result for outcome in outcomes]
                if not round2_results:
                    raise ValueError(f"No successful R2 results for {dimension.key}")
                if not round2_was_stored:
                    for outcome in outcomes:
                        result = outcome.result
                        db.add(
                            DimensionScore(
                                task_id=task.id,
                                dimension_key=dimension.key,
                                model_name=result.model_name,
                                score=result.score,
                                evidence_quotes=result.evidence_quotes,
                                analysis=result.analysis,
                                structured_payload=outcome.raw_payload,
                                round_number=2,
                            )
                        )
                round2_report = calculate_reliability(
                    dimension.key,
                    round2_results,
                    std_threshold=framework.std_threshold,
                )
                unresolved = cross_review.requires_expert_review(round2_report.std)
                existing_round2_reliability = (
                    db.query(ReliabilityResult)
                    .filter(
                        ReliabilityResult.task_id == task.id,
                        ReliabilityResult.dimension_key == dimension.key,
                        ReliabilityResult.round_number == 2,
                    )
                    .first()
                )
                if existing_round2_reliability is None:
                    db.add(
                        ReliabilityResult(
                            task_id=task.id,
                            dimension_key=dimension.key,
                            mean_score=round2_report.mean,
                            std_score=round2_report.std,
                            is_high_confidence=round2_report.is_high_confidence,
                            model_scores=round2_report.model_scores,
                            confidence_level=_confidence_level(round2_report.std),
                            requires_evidence_supplement=unresolved,
                            divergence_description=(
                                "R2 后仍超过 8 分，交专家复核" if unresolved else ""
                            ),
                            round_number=2,
                        )
                    )
                if unresolved:
                    task.manual_review_requested = True
                final_results = round2_results
                final_report = round2_report
                db.commit()
                mark_model_results(
                    db,
                    task.id,
                    phase="six_dimension_r2",
                    dimension_key=dimension.key,
                    model_names=[result.model_name for result in round2_results],
                )

            for result in final_results:
                per_model_scores.setdefault(result.model_name, {})[dimension.key] = (
                    result.score
                )
            reliability_reports.append(final_report)
            dimension_means[dimension.key] = final_report.mean
            db.commit()

        task.final_round = 2 if cross_review is not None else 1

        # 先按 v2.45 scoring_protocol (core_ceiling_bonus) 算出最终分
        # 用于 contradiction_triggers 判定（修复 #4：不再用维度均值近似）
        scoring_protocol = framework.raw_config.get("scoring_protocol")
        dimension_weights = {d.key: d.weight for d in framework.dimensions}
        final_score_estimate = calculate_weighted_total(
            dimension_scores=dimension_means,
            scoring_protocol=scoring_protocol,
            dimension_weights=dimension_weights,
        )

        # v2.45+ D 路径第 3 阶段：自主知识体系信号校验（仅当 framework 声明时激活）
        signal_result = None
        contradiction_rules: list[str] = []
        if framework.autonomous_knowledge_signals is not None:
            for name in actual_provider_names:
                set_work_status(
                    db,
                    task.id,
                    f"signal:{name}",
                    "running",
                    commit=False,
                )
            db.commit()
            signal_results = await run_signal_check_multi(
                providers,
                framework,
                processed_paper,
                task.id,
                db,
            )
            provider_names = [p.model_name for p in providers]
            agg_strategy = framework.autonomous_knowledge_signals.get(
                "quantification", {}
            ).get("aggregation_strategy")
            signal_result = aggregate_signal_results(
                signal_results, provider_names, aggregation_strategy=agg_strategy
            )
            _, rule_ids = check_contradiction_triggers(
                signal_result, reliability_reports, framework, final_score_estimate
            )
            contradiction_rules = rule_ids
            paper.signal_check_result = signal_to_dict(signal_result)
            db.add(paper)
            db.commit()
            for name in actual_provider_names:
                set_work_status(
                    db,
                    task.id,
                    f"signal:{name}",
                    "completed",
                    commit=False,
                )
            db.commit()

        # 聚合契约输出（所有框架都走此路径，旧框架的 precheck.conclusion 为 None 时用默认值）
        agg = aggregate_result(
            dimension_scores=dimension_means,
            precheck_result=precheck,
            signal_result=signal_result,
            reliability_reports=reliability_reports,
            framework=framework,
            contradiction_rules=contradiction_rules,
            per_model_scores=per_model_scores,
        )
        paper.aggregate_result = aggregate_result_to_dict(agg)
        # 修复 #1: 预检层复核（boundary / obviously_ineligible）与评价层复核都进队列
        if agg.review_status == "required":
            task.manual_review_requested = True
        # 修复 #5: 信号校验完成后把四信号反填到 precheck_result.triggered_signals
        if signal_result is not None and precheck.triggered_signals is None:
            precheck.triggered_signals = {
                "involves_china_issues": signal_result.china_problem_centered
                or "uncertain",
                "has_legal_question": (
                    signal_result.verifiable_concept_or_thesis or "uncertain"
                ),
                "china_practice_explanation_attempted": (
                    signal_result.china_practice_explanation_attempted or "uncertain"
                ),
                "theory_transformation_or_verifiable_thesis": (
                    signal_result.external_theory_transformation or "uncertain"
                ),
            }
            paper.precheck_result = precheck.model_dump()
        db.add(paper)
        db.add(task)
        db.commit()

        summary = summarize_reliability(reliability_reports)
        ensure_valid_task_transition(task.status, "completed")
        task.status = "completed"
        paper.status = "completed"
        db.add(task)
        db.add(paper)
        db.commit()
        set_work_status(db, task.id, "report", "running")
        generate_reports_for_task(db, task.id)
        set_work_status(db, task.id, "report", "completed")
        return {
            "task_status": task.status,
            "paper_status": paper.status,
            "precheck_status": paper.precheck_status,
            "reliability_summary": summary,
            "signal_check_triggered_rules": contradiction_rules,
            "aggregate_final_score": agg.final_score,
            "review_status": agg.review_status,
            "review_level": agg.review_level,
        }
    except Exception as exc:
        running_unit = (
            db.query(EvaluationWorkUnit)
            .filter(
                EvaluationWorkUnit.task_id == task.id,
                EvaluationWorkUnit.status == "running",
            )
            .first()
        )
        if running_unit is not None:
            set_work_status(
                db,
                task.id,
                running_unit.unit_key,
                "failed",
                failure_detail=str(exc),
            )
        ensure_valid_task_transition(task.status, "recovering")
        task.status = "recovering"
        task.failure_stage = "evaluation"
        task.failure_detail = str(exc)
        paper.status = "recovering"
        db.add(task)
        db.add(paper)
        db.commit()
        raise
