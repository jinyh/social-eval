from __future__ import annotations

import json

from sqlalchemy.orm import Session

from src.editorial.ai_calls import generate_json_with_audit
from src.editorial.policy import EditorialPolicy
from src.evaluation.providers.base import BaseProvider
from src.models.editorial import EditorialOpinion


_REQUIRED_SYNTHESIS_FIELDS = {
    "synthesis",
    "consensus_points",
    "disagreement_points",
    "priority_issues",
    "modification_suggestions",
}


def _validate_synthesis(payload: dict) -> None:
    missing = sorted(_REQUIRED_SYNTHESIS_FIELDS - set(payload))
    if missing:
        raise ValueError(f"综合摘要缺少字段：{'、'.join(missing)}")
    for key in _REQUIRED_SYNTHESIS_FIELDS - {"synthesis"}:
        if not isinstance(payload[key], list):
            raise ValueError(f"综合摘要字段 {key} 必须为列表")


async def generate_editorial_opinions(
    db: Session,
    *,
    submission_id: str,
    task_id: str,
    providers: list[BaseProvider],
    policy: EditorialPolicy,
    anonymized_text: str,
    evaluation_context: dict,
) -> list[EditorialOpinion]:
    """基于四模型既有结果生成一份综合摘要，不重复调用全文独立意见。"""

    del anonymized_text  # 综合阶段只使用已持久化的评分、证据和分歧摘要。
    existing = (
        db.query(EditorialOpinion)
        .filter(
            EditorialOpinion.submission_id == submission_id,
            EditorialOpinion.opinion_type == "ai_synthesis",
        )
        .order_by(EditorialOpinion.version.desc())
        .first()
    )
    if existing is not None:
        return [existing]
    if not providers:
        raise ValueError("生成综合摘要至少需要一个已配置模型")

    context = json.dumps(evaluation_context, ensure_ascii=False)
    base_prompt = policy.opinion["synthesis_prompt_template"]
    last_error: ValueError | None = None
    for attempt in range(2):
        retry_notice = (
            "\n\n上一次输出不符合契约。不得改字段名，必须严格按约定 JSON 输出。"
            if attempt
            else ""
        )
        payload = await generate_json_with_audit(
            db,
            task_id=task_id,
            provider=providers[0],
            call_type="editorial_opinion_synthesis",
            prompt=base_prompt
            + retry_notice
            + "\n\n四模型评价、分歧与其他辅助材料：\n"
            + context,
            dimension_key="__opinion_synthesis__",
        )
        try:
            _validate_synthesis(payload)
            break
        except ValueError as exc:
            last_error = exc
    else:
        raise ValueError(f"综合摘要连续两次不符合契约：{last_error}")

    synthesis = EditorialOpinion(
        submission_id=submission_id,
        opinion_type="ai_synthesis",
        version=1,
        sequence=1,
        content=payload,
        model_name=providers[0].model_name,
        provider_name=providers[0].__class__.__name__,
        is_locked=True,
    )
    db.add(synthesis)
    db.commit()
    db.refresh(synthesis)
    return [synthesis]
