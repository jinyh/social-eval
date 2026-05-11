"""第 3 阶段：自主知识体系信号校验（v0.14 规程 §2.3.5 / §5 / §7.3）。

独立的检查步骤，不是第七个评分维度，不进入基础分公式。
只整理文内可观察的自主知识体系信号，用于辅助六维评分和触发评价层复核。

仅当 framework.autonomous_knowledge_signals 被声明时激活（v2.45+）。
失败时返回降级结果（triggers_review=True），不阻塞主流程。

v2.46+: 多模型并发评估 + 激进聚合（取 max），不走 GPT-5.5 仲裁。
"""

from __future__ import annotations

import asyncio
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


def _signal_value_to_score(value: Any) -> int:
    normalized = str(value or "uncertain").strip().lower()
    if normalized in ("yes", "sufficient", "not_applicable"):
        return 2
    if normalized in ("partial", "uncertain"):
        return 1
    return 0


def _signal_strength(total: int) -> str:
    if total >= 7:
        return "strong"
    if total >= 4:
        return "medium"
    if total >= 1:
        return "weak"
    return "absent"


def _build_signal_result(payload: dict[str, Any]) -> SignalCheckResult:
    """把 provider 返回的 JSON payload 装配为 SignalCheckResult。

    同时填充扁平四类信号字段（v0.14 §7.3 契约）和 legacy signals 列表字段
    （与现有测试兼容）。
    """

    evidence = list(payload.get("evidence_quotes", []) or [])
    signal_scores = {
        key: _signal_value_to_score(payload.get(key, "uncertain"))
        for key in _CORE_SIGNAL_KEYS
    }
    autonomous_signal_score = sum(signal_scores.values())
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
        signal_scores=signal_scores,
        autonomous_signal_score=autonomous_signal_score,
        autonomous_signal_strength=_signal_strength(autonomous_signal_score),
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


async def run_signal_check_multi(
    providers: list[BaseProvider],
    framework: Framework,
    paper: ProcessedPaper,
    task_id: str,
    db: Session | None = None,
    retry_attempts: int = 2,
) -> list[SignalCheckResult]:
    """对所有 providers 并发执行信号校验，返回成功结果列表。"""

    tasks = [
        run_signal_check(p, framework, paper, task_id, db, retry_attempts)
        for p in providers
    ]
    results = await asyncio.gather(*tasks)
    # 过滤掉完全失败降级的结果（仅当有成功结果时）
    successful = [r for r in results if not (r.triggers_review and r.review_reason and r.review_reason.startswith("signal_check_failed"))]
    return successful if successful else list(results)


def aggregate_signal_results(
    results: list[SignalCheckResult],
    provider_names: list[str] | None = None,
) -> SignalCheckResult:
    """激进聚合：对 signal_scores 各项取 max，暴露 agreement 标记。

    策略：宁可多标不漏，下游有专家复核兜底。
    """

    if len(results) == 1:
        results[0].signal_model_agreement = True
        return results[0]

    if not results:
        return SignalCheckResult(
            triggers_review=True,
            review_reason="signal_check_failed: all providers failed",
        )

    # 收集各模型的 signal_scores
    all_model_scores: dict[str, dict[str, int]] = {}
    for i, r in enumerate(results):
        name = provider_names[i] if provider_names and i < len(provider_names) else f"model_{i}"
        all_model_scores[name] = dict(r.signal_scores) if r.signal_scores else {}

    # 激进聚合：每项取 max
    aggregated_scores: dict[str, int] = {}
    for key in _CORE_SIGNAL_KEYS:
        values = [r.signal_scores.get(key, 0) for r in results]
        aggregated_scores[key] = max(values)

    autonomous_signal_score = sum(aggregated_scores.values())

    # 判断 agreement：四项 signal_scores 完全一致
    first_scores = results[0].signal_scores
    agreement = all(
        r.signal_scores.get(key, 0) == first_scores.get(key, 0)
        for r in results[1:]
        for key in _CORE_SIGNAL_KEYS
    )

    # 四项核心判断字段：取对应 score 最高的那个模型的值
    best_result_per_key: dict[str, SignalCheckResult] = {}
    for key in _CORE_SIGNAL_KEYS:
        best_idx = max(range(len(results)), key=lambda i: results[i].signal_scores.get(key, 0))
        best_result_per_key[key] = results[best_idx]

    # evidence_quotes 合并去重
    all_quotes: list[str] = []
    seen: set[str] = set()
    for r in results:
        for q in r.evidence_quotes:
            if q not in seen:
                all_quotes.append(q)
                seen.add(q)

    # risks 合并去重
    all_risks: list[str] = []
    seen_risks: set[str] = set()
    for r in results:
        for risk in r.risks:
            if risk not in seen_risks:
                all_risks.append(risk)
                seen_risks.add(risk)

    # triggers_review: OR 逻辑
    any_triggers = any(r.triggers_review for r in results)
    review_reasons = [r.review_reason for r in results if r.triggers_review and r.review_reason]

    return SignalCheckResult(
        china_problem_centered=best_result_per_key["china_problem_centered"].china_problem_centered,
        china_practice_explanation_attempted=best_result_per_key["china_practice_explanation_attempted"].china_practice_explanation_attempted,
        external_theory_transformation=best_result_per_key["external_theory_transformation"].external_theory_transformation,
        verifiable_concept_or_thesis=best_result_per_key["verifiable_concept_or_thesis"].verifiable_concept_or_thesis,
        involves_special_chinese_institutional_issue=results[0].involves_special_chinese_institutional_issue,
        issue_types=list({t for r in results for t in r.issue_types}),
        uses_traditional_cultural_resource=results[0].uses_traditional_cultural_resource,
        evidence_quotes=all_quotes,
        risks=all_risks,
        triggers_review=any_triggers,
        review_reason="; ".join(review_reasons) if review_reasons else None,
        signal_scores=aggregated_scores,
        autonomous_signal_score=autonomous_signal_score,
        autonomous_signal_strength=_signal_strength(autonomous_signal_score),
        signal_model_agreement=agreement,
        per_model_signal_scores=all_model_scores,
    )
