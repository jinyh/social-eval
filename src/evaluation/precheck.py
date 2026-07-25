from __future__ import annotations

import asyncio
import time
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from src.core.config import settings
from src.core.exceptions import ProviderTimeoutError
from src.evaluation.call_logger import log_call
from src.evaluation.prompt_builder import build_precheck_prompt
from src.evaluation.providers.base import BaseProvider
from src.ingestion.schemas import ProcessedPaper
from src.knowledge.schemas import Framework


# v0.14 规程 §7.2 的 conclusion 字段枚举
# 映射依据（对应 v0.15 §2.2 三分流）：
# - pass / manual_review（旧"单模型提示风险"）→ 进评分
# - conditional_pass（v2.5+ 的"带风险可评"）→ v0.15 口径视为"边界进入评分并标记复核"
# - reject → 明显不适格（不进入评分，需人工确认）
_CONCLUSION_MAPPING = {
    "pass": "enter_six_dimension_review",
    "conditional_pass": "boundary_review",
    "manual_review": "boundary_review",
    "reject": "obviously_ineligible",
}

# enter_six_dimension_review 字段（§7.2 要求）的三档值
_ENTER_FIELD_MAPPING = {
    "enter_six_dimension_review": "yes",
    "boundary_review": "boundary",
    "obviously_ineligible": "no",
}


class PrecheckResult(BaseModel):
    """预检结果。

    遗留字段（status/issues/recommendation）保持不变，下游旧代码仍可读。
    v0.14 契约字段（conclusion 等）仅在 framework 声明 autonomous_knowledge_signals
    时由适配层填充（v2.45+）。
    """

    # 遗留字段（v2.0-v2.44 共用）
    status: str
    issues: list[str] = Field(default_factory=list)
    recommendation: str = ""

    # v0.14 规程 §7.2 契约字段（v2.45+ 由适配层填充）
    conclusion: str | None = None
    enter_six_dimension_review: str | None = None  # yes | boundary | no
    triggered_signals: dict[str, str] | None = None
    evidence_quotes: list[str] = Field(default_factory=list)
    boundary_reasons: list[str] = Field(default_factory=list)
    obviously_ineligible_reasons: list[str] = Field(default_factory=list)
    requires_manual_confirmation: bool | None = None

    # v2.46 / v0.16: split text extraction quality from project-scope routing.
    text_quality_gate: dict[str, Any] | None = None
    project_scope_precheck: dict[str, Any] | None = None

    model_config = ConfigDict(extra="allow")


def _adapt_to_v014_contract(
    result: PrecheckResult, framework: Framework
) -> PrecheckResult:
    """v2.45 适配层：把遗留 status 字段映射为 v0.14 规程要求的 conclusion 字段。

    仅当 framework 声明了 autonomous_knowledge_signals 区块时激活（即 v2.45+）。
    旧框架（v2.0/v2.8/v2.44 等）直接返回原 result，行为不变。

    triggered_signals 不在此填充——由 aggregate_result 根据 SignalCheckResult 返填
    （v0.14 规程规定预检阶段的"四信号"与信号校验阶段的"四信号"是同一组定义）。
    """
    if framework.autonomous_knowledge_signals is None:
        return result

    explicit_scope = bool(
        framework.raw_config.get("precheck", {}).get("mode")
        == "text_quality_and_project_scope"
    )
    if explicit_scope and result.conclusion in _ENTER_FIELD_MAPPING:
        conclusion = result.conclusion
        triggered_signals = result.triggered_signals
        if triggered_signals is None and result.project_scope_precheck:
            raw_signals = result.project_scope_precheck.get("triggered_signals")
            if isinstance(raw_signals, dict):
                triggered_signals = {str(k): str(v) for k, v in raw_signals.items()}
        requires_manual = conclusion != "enter_six_dimension_review"
    else:
        conclusion = _CONCLUSION_MAPPING.get(
            result.status, "enter_six_dimension_review"
        )
        triggered_signals = result.triggered_signals
        # conditional_pass / manual_review / reject 都需要人工干预
        requires_manual = result.status in (
            "conditional_pass",
            "manual_review",
            "reject",
        )

    return result.model_copy(
        update={
            "conclusion": conclusion,
            "enter_six_dimension_review": _ENTER_FIELD_MAPPING[conclusion],
            "triggered_signals": triggered_signals,
            "requires_manual_confirmation": requires_manual,
            "boundary_reasons": result.issues
            if conclusion == "boundary_review"
            else [],
            "obviously_ineligible_reasons": (
                result.issues if conclusion == "obviously_ineligible" else []
            ),
        }
    )


async def run_precheck(
    provider: BaseProvider,
    framework: Framework,
    paper: ProcessedPaper,
    task_id: str,
    db: Session,
    retry_attempts: int = 3,
) -> PrecheckResult:
    prompt = build_precheck_prompt(framework, paper)
    last_error: Exception | None = None

    for _ in range(retry_attempts):
        start = time.time()
        try:
            timeout = getattr(provider, "timeout", settings.provider_timeout)
            try:
                payload = await asyncio.wait_for(
                    provider.generate_json_response(prompt),
                    timeout=timeout,
                )
            except asyncio.TimeoutError as exc:
                raise ProviderTimeoutError(provider.model_name, timeout) from exc
            log_call(
                db,
                task_id,
                provider.model_name,
                "__precheck__",
                prompt,
                str(payload),
                start,
                call_type="precheck",
                provider_name=provider.__class__.__name__,
            )
            result = PrecheckResult(**payload)
            return _adapt_to_v014_contract(result, framework)
        except Exception as exc:
            last_error = exc
            log_call(
                db,
                task_id,
                provider.model_name,
                "__precheck__",
                prompt,
                str(exc),
                start,
                call_type="precheck",
                provider_name=provider.__class__.__name__,
                status="failed",
                failure_detail=str(exc),
            )
    raise last_error or RuntimeError("Precheck failed")
