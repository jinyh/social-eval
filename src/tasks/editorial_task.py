from __future__ import annotations

import asyncio

from src.core.database import SessionLocal
from src.editorial.workflow import run_editorial_pipeline
from src.tasks.celery_app import celery_app


@celery_app.task(name="socialeval.run_editorial_submission")
def run_editorial_submission(submission_id: str) -> None:
    db = SessionLocal()
    try:
        asyncio.run(run_editorial_pipeline(submission_id, db))
    finally:
        db.close()


def dispatch_editorial_submission(submission_id: str) -> None:
    run_editorial_submission.delay(submission_id)
