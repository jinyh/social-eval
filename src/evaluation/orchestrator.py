from __future__ import annotations

import json

from sqlalchemy.orm import Session

from src.core.state_machine import ensure_valid_task_transition
from src.evaluation.concurrent_evaluator import evaluate_dimension_concurrent
from src.evaluation.defaults import (
    DEFAULT_FRAMEWORK_PATH,
    DEFAULT_PROVIDER_NAMES,
    MANDATORY_REVIEW_FLAGS,
    MANUAL_REVIEW_PRECHECK_STATUSES,
)
from src.evaluation.precheck import run_precheck
from src.evaluation.providers.factory import create_providers
from src.ingestion.preprocessor import process_file
from src.knowledge.loader import load_framework
from src.models.evaluation import DimensionScore, EvaluationTask
from src.models.paper import Paper
from src.models.reliability import ReliabilityResult
from src.reporting.versioning import generate_reports_for_task
from src.reliability.calculator import calculate_reliability
from src.reliability.threshold_checker import summarize_reliability


def _has_actionable_review_flags(flags: list[str]) -> bool:
    return any(flag and flag != "none" for flag in flags)


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

    framework = load_framework(task.framework_path or DEFAULT_FRAMEWORK_PATH)
    provider_names = json.loads(task.provider_names or json.dumps(DEFAULT_PROVIDER_NAMES))
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
        if precheck.status in MANUAL_REVIEW_PRECHECK_STATUSES or _has_actionable_review_flags(
            precheck.review_flags
        ):
            task.manual_review_requested = True
        db.add(paper)
        db.add(task)
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
        mandatory_review_requested = task.manual_review_requested
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

            if any(
                flag in MANDATORY_REVIEW_FLAGS
                for result in results
                for flag in result.review_flags
            ):
                mandatory_review_requested = True

            for result in results:
                db.add(
                    DimensionScore(
                        task_id=task.id,
                        dimension_key=dimension.key,
                        model_name=result.model_name,
                        score=result.score,
                        evidence_quotes=result.evidence_quotes,
                        analysis=result.model_dump_json(),
                    )
                )

            report = calculate_reliability(
                dimension.key,
                results,
                std_threshold=framework.std_threshold,
            )
            reliability_reports.append(report)
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

        summary = summarize_reliability(reliability_reports)
        ensure_valid_task_transition(task.status, "completed")
        task.status = "completed"
        task.manual_review_requested = mandatory_review_requested
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
