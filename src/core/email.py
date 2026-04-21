from __future__ import annotations

from src.core.logging import logger


def send_review_assignment_email(
    *,
    expert_email: str,
    task_id: str,
    paper_title: str,
    summary: str,
) -> None:
    logger.info(
        "review_assignment_email",
        extra={
            "expert_email": expert_email,
            "task_id": task_id,
            "paper_title": paper_title,
            "summary": summary,
        },
    )
