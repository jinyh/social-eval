from __future__ import annotations

import json
import time
from typing import Any

from sqlalchemy.orm import Session

from src.core.time import utc_now
from src.evaluation.providers.base import BaseProvider
from src.models.evaluation import AICallLog


async def generate_json_with_audit(
    db: Session,
    *,
    task_id: str,
    provider: BaseProvider,
    call_type: str,
    prompt: str,
    dimension_key: str = "__editorial__",
    round_number: int = 1,
) -> dict[str, Any]:
    """通过 provider 抽象调用模型，并持久化成功或失败的完整记录。"""

    started_at = utc_now()
    started = time.monotonic()
    try:
        payload = await provider.generate_json_response(prompt)
    except Exception as exc:
        completed_at = utc_now()
        raw_response = getattr(exc, "raw_response", None)
        db.add(
            AICallLog(
                task_id=task_id,
                model_name=provider.model_name,
                provider_name=provider.__class__.__name__,
                dimension_key=dimension_key,
                prompt_text=prompt,
                response_text=str(raw_response or ""),
                duration_ms=int((time.monotonic() - started) * 1000),
                round_number=round_number,
                call_type=call_type,
                status="failed",
                failure_detail=str(exc),
                started_at=started_at,
                completed_at=completed_at,
            )
        )
        db.commit()
        raise

    completed_at = utc_now()
    db.add(
        AICallLog(
            task_id=task_id,
            model_name=provider.model_name,
            provider_name=provider.__class__.__name__,
            dimension_key=dimension_key,
            prompt_text=prompt,
            response_text=json.dumps(payload, ensure_ascii=False),
            duration_ms=int((time.monotonic() - started) * 1000),
            round_number=round_number,
            call_type=call_type,
            status="success",
            started_at=started_at,
            completed_at=completed_at,
        )
    )
    db.commit()
    return payload
