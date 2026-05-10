"""第 3 阶段：自主知识体系信号校验（v0.14 规程 §2.3.5 / §5 / §7.3）。

独立的检查步骤，不是第七个评分维度，不进入基础分公式。
只整理文内可观察的自主知识体系信号，用于辅助六维评分和触发评价层复核。

仅当 framework.autonomous_knowledge_signals 被声明时激活（v2.45+）。
失败时返回降级结果（triggers_review=True），不阻塞主流程。
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from sqlalchemy.orm import Session

from src.evaluation.call_logger import log_call
from src.evaluation.prompt_builder import build_signal_check_prompt
from src.evaluation.providers.base import BaseProvider
from src.evaluation.schemas import SignalCheckResult, SignalJudgment
from src.ingestion.schemas import ProcessedPaper
from src.knowledge.schemas import Framework
from src.reliability.schemas import ReliabilityReport

logger = logging.getLogger(__name__)

SIGNAL_CHECK_DIMENSION_KEY = "__signal_check__"

# v0.14 §5.2 的四类核心信号 key，顺序与规程一致
_CORE_SIGNAL_KEYS = (
    "china_problem_centered",
    "china_practice_explanation_attempted",
    "external_theory_transformation",
    "verifiable_concept_or_thesis",
)


def _build_signal_result(payload: dict[str, Any]) -> SignalCheckResult:
    """把 provider 返回的 JSON payload 装配为 SignalCheckResult。

    同时填充扁平四类信号字段（v0.14 §7.3 契约）和 legacy signals 列表字段
    （与现有测试兼容）。
    """

    evidence = list(payload.get("evidence_quotes", []) or [])
    signals = []
    for key in _CORE_SIGNAL_KEYS:
        judgment = payload.get(key, "uncertain")
        quote = evidence[0] if evidence else None
        signals.append(
            SignalJudgment(signal_key=key, judgment=judgment, evidence_quote=quote)
        )

    return SignalCheckResult(
        china_problem_centered=payload.get("china_problem_centered"),
        china_practice_explanation_attempted=payload.get(
            "china_practice_explanation_attempted"
        ),
        external_theory_transformation=payload.get("external_theory_transformation"),
        verifiable_concept_or_thesis=payload.get("verifiable_concept_or_thesis"),
        involves_special_chinese_institutional_issue=payload.get(
            "involves_special_chinese_institutional_issue"
        ),
        issue_types=list(payload.get("issue_types", []) or []),
        uses_traditional_cultural_resource=payload.get(
            "uses_traditional_cultural_resource"
        ),
        evidence_quotes=evidence,
        risks=list(payload.get("risks", []) or []),
        triggers_review=bool(payload.get("triggers_review", False)),
        review_reason=payload.get("review_reason"),
        signals=signals,
    )


async def run_signal_check(
    provider: BaseProvider,
    framework: Framework,
    paper: ProcessedPaper,
    task_id: str,
    db: Session | None = None,
    retry_attempts: int = 2,
) -> SignalCheckResult:
    """执行第 3 阶段信号校验。失败降级为 triggers_review=True。"""

    prompt = build_signal_check_prompt(framework, paper)
    start = time.time()
    last_error: Exception | None = None

    for _ in range(retry_attempts):
        try:
            payload = await provider.generate_json_response(prompt)
            if db is not None:
                log_call(
                    db,
                    task_id,
                    provider.model_name,
                    SIGNAL_CHECK_DIMENSION_KEY,
                    prompt,
                    json.dumps(payload, ensure_ascii=False),
                    start,
                )
            return _build_signal_result(payload)
        except Exception as exc:
            last_error = exc
            logger.warning("signal_check attempt failed: %s", exc)

    # 降级：不阻塞主流程，返回触发复核的空结果
    if db is not None:
        log_call(
            db,
            task_id,
            provider.model_name,
            SIGNAL_CHECK_DIMENSION_KEY,
            prompt,
            f"[FAILED] {last_error}",
            start,
        )
    return SignalCheckResult(
        triggers_review=True,
        review_reason=f"signal_check_failed: {last_error}",
    )


def _dimension_mean(
    reliability_reports: list[ReliabilityReport], dimension_key: str
) -> float | None:
    for report in reliability_reports:
        if report.dimension_key == dimension_key:
            return report.mean
    return None


def _all_signals_yes(signal: SignalCheckResult) -> bool:
    return (
        signal.china_problem_centered == "yes"
        and signal.china_practice_explanation_attempted == "yes"
        and signal.external_theory_transformation in ("sufficient", "partial")
        and signal.verifiable_concept_or_thesis == "yes"
    )


def check_contradiction_triggers(
    signal: SignalCheckResult,
    reliability_reports: list[ReliabilityReport],
    framework: Framework,
    total_score: float,
) -> tuple[bool, list[str]]:
    """按 autonomous_knowledge_signals.contradiction_triggers 判定是否触发评价层复核。

    返回 (是否触发, 触发规则 ID 列表)。

    对应 v0.14 §6.1.2 的四条规则：
    - total_high_but_no_china_problem
    - total_low_but_all_signals_yes
    - high_originality_but_no_verifiable_thesis
    - slogan_heavy_but_no_legal_question（由 signal.triggers_review 自报）
    """

    if framework.autonomous_knowledge_signals is None:
        return False, []

    triggered: list[str] = []

    # signal 自身声明的触发（例如 slogan_heavy 由 prompt 侧判定）
    if signal.triggers_review and signal.review_reason:
        triggered.append(signal.review_reason)

    # 规则 1: 总分>70 但 china_problem_centered / china_practice_explanation_attempted == no
    if total_score > 70 and (
        signal.china_problem_centered == "no"
        or signal.china_practice_explanation_attempted == "no"
    ):
        triggered.append("total_high_but_no_china_problem")

    # 规则 2: 总分<50 但四信号全部 == yes（疑似 AI 误判）
    if total_score < 50 and _all_signals_yes(signal):
        triggered.append("total_low_but_all_signals_yes")

    # 规则 3: 研究创新性 >= 80 但 verifiable_concept_or_thesis == no
    originality_mean = _dimension_mean(reliability_reports, "problem_originality")
    if (
        originality_mean is not None
        and originality_mean >= 80
        and signal.verifiable_concept_or_thesis == "no"
    ):
        triggered.append("high_originality_but_no_verifiable_thesis")

    return len(triggered) > 0, triggered


def signal_to_dict(signal: SignalCheckResult) -> dict[str, Any]:
    """序列化为 v0.14 §7.3 契约要求的 JSON 结构（用于 paper.signal_check_result 落库）。"""

    return signal.model_dump(exclude_none=True, exclude={"signals"})
