from __future__ import annotations

import asyncio

from src.core.database import SessionLocal
from src.evaluation.orchestrator import run_evaluation_pipeline
from src.tasks.celery_app import celery_app


@celery_app.task(name="socialeval.run_evaluation_task")
def run_evaluation_task(task_id: str) -> None:
    db = SessionLocal()
    try:
        asyncio.run(run_evaluation_pipeline(task_id, db))
    finally:
        db.close()


def dispatch_evaluation_task(task_id: str) -> None:
    run_evaluation_task.delay(task_id)
