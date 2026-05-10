from __future__ import annotations

import time

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.evaluation.call_logger import log_call
from src.evaluation.prompt_builder import build_precheck_prompt
from src.evaluation.providers.base import BaseProvider
from src.ingestion.schemas import ProcessedPaper
from src.knowledge.schemas import Framework


# v0.14 规程 §7.2 的 conclusion 字段枚举
_CONCLUSION_MAPPING = {
    "pass": "enter_six_dimension_review",
    "conditional_pass": "enter_six_dimension_review",
    "manual_review": "boundary_review",
    "reject": "obviously_ineligible",
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
    triggered_signals: dict[str, str] | None = None
    evidence_quotes: list[str] = Field(default_factory=list)
    boundary_reasons: list[str] = Field(default_factory=list)
    obviously_ineligible_reasons: list[str] = Field(default_factory=list)
    requires_manual_confirmation: bool | None = None


def _adapt_to_v014_contract(
    result: PrecheckResult, framework: Framework
) -> PrecheckResult:
    """v2.45 适配层：把遗留 status 字段映射为 v0.14 规程要求的 conclusion 字段。

    仅当 framework 声明了 autonomous_knowledge_signals 区块时激活（即 v2.45+）。
    旧框架（v2.0/v2.8/v2.44 等）直接返回原 result，行为不变。
    """
    if framework.autonomous_knowledge_signals is None:
        return result

    conclusion = _CONCLUSION_MAPPING.get(result.status, "enter_six_dimension_review")
    requires_manual = result.status in ("manual_review", "reject")

    return result.model_copy(
        update={
            "conclusion": conclusion,
            "requires_manual_confirmation": requires_manual,
            # 保留原 issues 作为 boundary_reasons / obviously_ineligible_reasons 的备用来源
            "boundary_reasons": result.issues if conclusion == "boundary_review" else [],
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
    start = time.time()
    last_error: Exception | None = None

    for _ in range(retry_attempts):
        try:
            payload = await provider.generate_json_response(prompt)
            log_call(
                db,
                task_id,
                provider.model_name,
                "__precheck__",
                prompt,
                str(payload),
                start,
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
        str(last_error),
        start,
    )
    raise last_error or RuntimeError("Precheck failed")
