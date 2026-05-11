from __future__ import annotations

import json
import logging

from sqlalchemy.orm import Session

from src.core.state_machine import ensure_valid_task_transition
from src.evaluation.concurrent_evaluator import evaluate_dimension_concurrent
from src.evaluation.precheck import run_precheck
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
from src.models.evaluation import DimensionScore, EvaluationTask
from src.models.paper import Paper
from src.models.reliability import ReliabilityResult
from src.reliability.calculator import calculate_reliability
from src.reliability.threshold_checker import summarize_reliability
from src.reporting.scoring import calculate_weighted_total
from src.reporting.versioning import generate_reports_for_task

logger = logging.getLogger(__name__)


async def run_evaluation_pipeline(
    task_id: str,
    db: Session,
    *,
    provider_factory=create_providers,
) -> dict:
    task = db.get(EvaluationTask, task_id)
    if task is None:
        raise ValueError(f"EvaluationTask {task_id} not found")

    paper = db.get(Paper, task.paper_id)
    if paper is None or not paper.file_path:
        raise ValueError(f"Paper for task {task_id} not found or missing file")

    framework = load_framework(task.framework_path or "configs/frameworks/law-v2.0-20260413.yaml")
    provider_names = json.loads(task.provider_names or '["openai","anthropic","deepseek"]')
    providers = provider_factory(provider_names)
    if not providers:
        raise ValueError("No providers configured")

    task.status = "processing"
    task.failure_stage = None
    task.failure_detail = None
    paper.status = "processing"
    db.add(task)
    db.add(paper)
    db.commit()

    try:
        processed_paper = process_file(paper.file_path)
        precheck = await run_precheck(
            providers[0],
            framework,
            processed_paper,
            task.id,
            db,
        )
        paper.precheck_status = precheck.status
        paper.precheck_result = precheck.model_dump()
        db.add(paper)
        db.commit()

        if precheck.status == "reject":
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
            generate_reports_for_task(db, task.id)
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
            results = await evaluate_dimension_concurrent(
                providers,
                dimension,
                processed_paper,
                task.id,
                db,
            )
            if not results:
                raise ValueError(f"No successful results for dimension {dimension.key}")

            for result in results:
                db.add(
                    DimensionScore(
                        task_id=task.id,
                        dimension_key=dimension.key,
                        model_name=result.model_name,
                        score=result.score,
                        evidence_quotes=result.evidence_quotes,
                        analysis=result.analysis,
                    )
                )
                per_model_scores.setdefault(result.model_name, {})[dimension.key] = (
                    result.score
                )

            report = calculate_reliability(
                dimension.key,
                results,
                std_threshold=framework.std_threshold,
            )
            reliability_reports.append(report)
            dimension_means[dimension.key] = report.mean
            db.add(
                ReliabilityResult(
                    task_id=task.id,
                    dimension_key=dimension.key,
                    mean_score=report.mean,
                    std_score=report.std,
                    is_high_confidence=report.is_high_confidence,
                    model_scores=report.model_scores,
                )
            )
            db.commit()

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
            signal_results = await run_signal_check_multi(
                providers,
                framework,
                processed_paper,
                task.id,
                db,
            )
            provider_names = [p.model_name for p in providers]
            agg_strategy = (
                framework.autonomous_knowledge_signals
                .get("quantification", {})
                .get("aggregation_strategy")
            )
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
                "involves_china_issues": signal_result.china_problem_centered or "uncertain",
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
        generate_reports_for_task(db, task.id)
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
        ensure_valid_task_transition(task.status, "recovering")
        task.status = "recovering"
        task.failure_stage = "evaluation"
        task.failure_detail = str(exc)
        paper.status = "recovering"
        db.add(task)
        db.add(paper)
        db.commit()
        raise
