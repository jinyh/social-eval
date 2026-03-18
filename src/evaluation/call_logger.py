import time
from sqlalchemy.orm import Session
from src.models.evaluation import AICallLog


def log_call(
    db: Session,
    task_id: str,
    model_name: str,
    dimension_key: str,
    prompt: str,
    response: str,
    start_time: float,
) -> None:
    duration_ms = int((time.time() - start_time) * 1000)
    log = AICallLog(
        task_id=task_id,
        model_name=model_name,
        dimension_key=dimension_key,
        prompt_text=prompt,
        response_text=response,
        duration_ms=duration_ms,
    )
    db.add(log)
    db.commit()
