from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from src.editorial.ai_calls import generate_json_with_audit
from src.editorial.policy import EditorialPolicy
from src.evaluation.providers.base import BaseProvider

FIT_STATUSES = {"pass", "boundary", "reject"}


def _format_fit_profile(profile: dict[str, Any]) -> str:
    """把版本化期刊口径整理为模型可核对的中文清单。"""

    labels = (
        ("accepted_scope", "收稿范围"),
        ("excluded_scope", "明确排除范围"),
        ("column_positioning", "栏目定位"),
        ("article_types", "稿件类型"),
        ("target_readers", "目标读者"),
    )
    lines = ["【本刊版本化适配口径】"]
    for key, label in labels:
        values = profile.get(key)
        if isinstance(values, list) and values:
            lines.append(f"{label}：" + "；".join(str(value) for value in values))
    special_notes = str(profile.get("special_notes") or "").strip()
    if special_notes:
        lines.append(f"特别说明：{special_notes}")
    lines.append("上述口径只用于适配性判断，不得替代六维学术质量评价。")
    return "\n".join(lines)


def _normalize_text_items(
    value: Any,
    *,
    keys: tuple[str, ...],
) -> list[str] | None:
    if not isinstance(value, list):
        return None
    normalized: list[str] = []
    for item in value:
        if isinstance(item, str) and item.strip():
            normalized.append(item.strip())
            continue
        if not isinstance(item, dict):
            return None
        text = next(
            (
                item.get(key).strip()
                for key in keys
                if isinstance(item.get(key), str) and item.get(key).strip()
            ),
            None,
        )
        if text is None:
            return None
        normalized.append(text)
    return normalized


def _validate_fit_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """严格校验期刊适配性契约，避免字段漂移后静默降级。"""

    required = {
        "status",
        "reasons",
        "evidence_quotes",
        "requires_editor_confirmation",
    }
    missing = sorted(required - set(payload))
    if missing:
        raise ValueError(f"期刊适配性结果缺少字段：{'、'.join(missing)}")
    status = payload["status"]
    if status not in FIT_STATUSES:
        raise ValueError(f"期刊适配性状态无效：{status}")
    reasons = _normalize_text_items(
        payload["reasons"],
        keys=("reason", "rationale", "summary", "text"),
    )
    evidence = _normalize_text_items(
        payload["evidence_quotes"],
        keys=("quote", "evidence_quote", "evidence", "text"),
    )
    if reasons is None:
        raise ValueError("期刊适配性理由必须是文字列表")
    if evidence is None:
        raise ValueError("期刊适配性证据必须是原文引文列表")
    if not isinstance(payload["requires_editor_confirmation"], bool):
        raise ValueError("期刊适配性人工确认字段必须为布尔值")
    return {
        "status": status,
        "reasons": reasons,
        "evidence_quotes": evidence,
        "requires_editor_confirmation": payload["requires_editor_confirmation"],
        "raw": payload,
    }


async def evaluate_journal_fit(
    db: Session,
    *,
    task_id: str,
    provider: BaseProvider,
    policy: EditorialPolicy,
    anonymized_text: str,
    journal_name: str,
    unit_name: str,
) -> dict[str, Any]:
    """执行独立于六维学术质量的期刊适配性检查。"""

    prompt_context = {
        **policy.profile,
        "journal_name": journal_name,
        "unit_name": unit_name,
    }
    prompt = policy.journal_fit["prompt_template"].format(**prompt_context)
    prompt += "\n\n" + _format_fit_profile(policy.profile)
    prompt += "\n\n输出契约：\n" + json.dumps(
        policy.journal_fit["output_contract"], ensure_ascii=False
    )
    prompt += "\n\n匿名稿正文：\n" + anonymized_text[:50_000]
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
            provider=provider,
            call_type="journal_fit",
            prompt=prompt + retry_notice,
            dimension_key="__journal_fit__",
        )
        try:
            return _validate_fit_payload(payload)
        except ValueError as exc:
            last_error = exc
    raise ValueError(f"期刊适配性结果连续两次不符合契约：{last_error}")
