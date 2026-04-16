from __future__ import annotations

from sqlalchemy.orm import Session

from src.models.evaluation import EvaluationTask
from src.models.paper import Paper
from src.models.reliability import ReliabilityResult


def list_review_queue(db: Session) -> list[dict]:
    queued_tasks = []
    tasks = db.query(EvaluationTask).all()
    for task in tasks:
        low_confidence_rows = (
            db.query(ReliabilityResult)
            .filter(ReliabilityResult.task_id == task.id, ReliabilityResult.is_high_confidence.is_(False))
            .all()
        )
        if not low_confidence_rows and not task.manual_review_requested and task.status != "reviewing":
            continue
        paper = db.get(Paper, task.paper_id)
        queued_tasks.append(
            {
                "task_id": task.id,
                "paper_id": task.paper_id,
                "paper_title": (paper.title if paper else None),
                "paper_status": paper.status if paper else None,
                "task_status": task.status,
                "low_confidence_dimensions": [row.dimension_key for row in low_confidence_rows],
            }
        )
    return queued_tasks
