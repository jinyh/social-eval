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
    check_contradiction_triggers,
    run_signal_check,
    signal_to_dict,
)
from src.ingestion.preprocessor import process_file
from src.knowledge.loader import load_framework
from src.models.evaluation import DimensionScore, EvaluationTask
from src.models.paper import Paper
from src.models.reliability import ReliabilityResult
from src.reliability.calculator import calculate_reliability
from src.reliability.threshold_checker import summarize_reliability
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
            }

        reliability_reports = []
        dimension_means: dict[str, float] = {}
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

        # v2.45 D 路径第 3 阶段：自主知识体系信号校验（仅当 framework 声明时激活）
        signal_result = None
        contradiction_rules: list[str] = []
        if framework.autonomous_knowledge_signals is not None:
            # 用总分的粗估值作为 contradiction_triggers 的输入
            # （此时 final_score 未算出；用基础分近似即可，四条规则阈值粒度粗）
            rough_total = sum(dimension_means.values()) / max(len(dimension_means), 1)
            signal_result = await run_signal_check(
                providers[0],
                framework,
                processed_paper,
                task.id,
                db,
            )
            triggered, rule_ids = check_contradiction_triggers(
                signal_result, reliability_reports, framework, rough_total
            )
            contradiction_rules = rule_ids
            paper.signal_check_result = signal_to_dict(signal_result)
            if triggered:
                task.manual_review_requested = True
            db.add(paper)
            db.add(task)
            db.commit()

        # 聚合契约输出（所有框架都走此路径，旧框架的 precheck.conclusion 为 None 时用默认值）
        agg = aggregate_result(
            dimension_scores=dimension_means,
            precheck_result=precheck,
            signal_result=signal_result,
            reliability_reports=reliability_reports,
            framework=framework,
            contradiction_rules=contradiction_rules,
        )
        paper.aggregate_result = aggregate_result_to_dict(agg)
        if agg.review_status == "required" and agg.review_level == "evaluation_level":
            task.manual_review_requested = True
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
