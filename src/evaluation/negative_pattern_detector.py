"""Stage A 负面模式检测器

独立于维度评分的短 prompt 检测器。从 YAML 加载 negative_patterns 配置，
调用 AI 检测负面模式，返回结构化 NegativePatternResult。

支持三种模式（由 YAML negative_patterns.mode 控制）：
- dry_run: 正常检测并记录结果，但不应用 ceiling
- enforce: 检测后代码层执行 min(stage_b_score, ceiling)
- disabled: 完全跳过 Stage A 调用
"""

from __future__ import annotations

import time
from typing import Any

from src.evaluation.prompt_builder import build_negative_pattern_prompt
from src.evaluation.providers.base import BaseProvider
from src.evaluation.schemas import NegativePatternFlag, NegativePatternResult
from src.ingestion.schemas import ProcessedPaper


def load_negative_patterns(raw_config: dict[str, Any]) -> dict[str, Any] | None:
    """从框架 raw_config 中加载 negative_patterns 配置。"""
    np_config = raw_config.get("negative_patterns")
    if not np_config:
        return None
    if np_config.get("mode") == "disabled":
        return None
    return np_config


def _parse_pattern_flags(raw: dict, patterns: list[dict]) -> list[NegativePatternFlag]:
    """解析 AI 返回的 pattern_flags，校验 pattern_id 合法性。"""
    valid_ids = {p["pattern_id"] for p in patterns}
    flags = []
    for item in raw.get("pattern_flags", []):
        pid = item.get("pattern_id", "")
        if pid not in valid_ids:
            continue
        pattern_config = next((p for p in patterns if p["pattern_id"] == pid), {})
        min_confidence = pattern_config.get("min_confidence", 0.65)
        confidence = float(item.get("confidence", 0.0))
        triggered = bool(item.get("triggered", False))
        severity = str(item.get("severity", "low"))

        # 置信度不足时降级为 not triggered
        if triggered and confidence < min_confidence:
            triggered = False
            severity = "low"

        ceiling = pattern_config.get("ceiling") if triggered else None

        flags.append(NegativePatternFlag(
            pattern_id=pid,
            triggered=triggered,
            severity=severity,
            score_ceiling=ceiling,
            confidence=confidence,
            evidence_quotes=item.get("evidence_quotes", []),
            rationale=item.get("rationale"),
        ))
    return flags


def _compute_applied_ceiling(flags: list[NegativePatternFlag]) -> int | None:
    """多个 pattern 触发时取最低 ceiling（最严格规则优先）。"""
    ceilings = [f.score_ceiling for f in flags if f.triggered and f.score_ceiling is not None]
    return min(ceilings) if ceilings else None


async def detect_negative_patterns(
    provider: BaseProvider,
    dimension_key: str,
    patterns: list[dict],
    paper: ProcessedPaper,
) -> NegativePatternResult:
    """对单个维度运行 Stage A 负面模式检测（批量模式，兼容旧接口）。"""
    prompt = build_negative_pattern_prompt(dimension_key, patterns, paper)

    start = time.time()
    try:
        raw = await provider.generate_json_response(prompt)
    except Exception:
        return NegativePatternResult(
            dimension=dimension_key,
            pattern_flags=[],
            applied_score_ceiling=None,
            requires_manual_review=True,
            model_name=provider.model_name,
        )
    _elapsed = time.time() - start  # noqa: F841 — Phase 1 审计日志使用

    if not isinstance(raw, dict):
        return NegativePatternResult(
            dimension=dimension_key,
            pattern_flags=[],
            applied_score_ceiling=None,
            requires_manual_review=True,
            model_name=provider.model_name,
        )

    flags = _parse_pattern_flags(raw, patterns)
    applied_ceiling = _compute_applied_ceiling(flags)

    return NegativePatternResult(
        dimension=dimension_key,
        pattern_flags=flags,
        applied_score_ceiling=applied_ceiling,
        requires_manual_review=applied_ceiling is not None,
        model_name=provider.model_name,
    )


async def _detect_single_pattern(
    provider: BaseProvider,
    dimension_key: str,
    pattern: dict,
    paper: ProcessedPaper,
) -> NegativePatternFlag:
    """对单个 pattern 独立调用 AI 检测（推荐模式）。"""
    from src.evaluation.prompt_builder import build_single_pattern_prompt

    prompt = build_single_pattern_prompt(dimension_key, pattern, paper)

    try:
        raw = await provider.generate_json_response(prompt)
    except Exception:
        return NegativePatternFlag(
            pattern_id=pattern["pattern_id"],
            triggered=False,
            severity="low",
            confidence=0.0,
            rationale="AI 调用失败",
        )

    if not isinstance(raw, dict):
        return NegativePatternFlag(
            pattern_id=pattern["pattern_id"],
            triggered=False,
            severity="low",
            confidence=0.0,
            rationale="AI 返回格式错误",
        )

    min_confidence = pattern.get("min_confidence", 0.65)
    confidence = float(raw.get("confidence", 0.0))
    triggered = bool(raw.get("triggered", False))
    severity = str(raw.get("severity", "low"))

    if triggered and confidence < min_confidence:
        triggered = False
        severity = "low"

    ceiling = pattern.get("ceiling") if triggered else None

    return NegativePatternFlag(
        pattern_id=pattern["pattern_id"],
        triggered=triggered,
        severity=severity,
        score_ceiling=ceiling,
        confidence=confidence,
        evidence_quotes=raw.get("evidence_quotes", []),
        rationale=raw.get("rationale"),
    )


async def detect_patterns_individually(
    provider: BaseProvider,
    dimension_key: str,
    patterns: list[dict],
    paper: ProcessedPaper,
) -> NegativePatternResult:
    """对单个维度逐个 pattern 独立检测（推荐模式）。"""
    import asyncio

    flags = await asyncio.gather(
        *[_detect_single_pattern(provider, dimension_key, p, paper)
          for p in patterns],
        return_exceptions=False,
    )
    flags = list(flags)
    applied_ceiling = _compute_applied_ceiling(flags)

    return NegativePatternResult(
        dimension=dimension_key,
        pattern_flags=flags,
        applied_score_ceiling=applied_ceiling,
        requires_manual_review=applied_ceiling is not None,
        model_name=provider.model_name,
    )


async def run_stage_a(
    providers: list[BaseProvider],
    dimension_key: str,
    patterns: list[dict],
    paper: ProcessedPaper,
    mode: str = "dry_run",
    single_pattern_mode: bool = True,
) -> list[NegativePatternResult]:
    """对多个模型并发运行 Stage A 检测。

    single_pattern_mode=True（默认）：每个 pattern 独立调用，避免相互干扰。
    single_pattern_mode=False：批量模式，一次调用检测所有 pattern。
    """
    import asyncio

    if mode == "disabled":
        return []

    if single_pattern_mode:
        results = await asyncio.gather(
            *[detect_patterns_individually(provider, dimension_key, patterns, paper)
              for provider in providers],
            return_exceptions=False,
        )
    else:
        results = await asyncio.gather(
            *[detect_negative_patterns(provider, dimension_key, patterns, paper)
              for provider in providers],
            return_exceptions=False,
        )
    return list(results)


def aggregate_stage_a_results(
    results: list[NegativePatternResult],
) -> tuple[int | None, bool]:
    """多模型一致性决策规则。

    返回 (applied_ceiling, requires_manual_review)。
    - 多数触发（>= 50% 模型命中同一 pattern）：应用 ceiling
    - 少数触发（仅 1 个模型命中）：不压分，标记 requires_manual_review
    - 全部触发：应用 ceiling
    """
    if not results:
        return None, False

    # 统计每个 pattern 被多少模型触发
    from collections import Counter
    pattern_trigger_count: Counter[str] = Counter()
    pattern_ceilings: dict[str, list[int]] = {}

    for r in results:
        for flag in r.pattern_flags:
            if flag.triggered:
                pattern_trigger_count[flag.pattern_id] += 1
                if flag.score_ceiling is not None:
                    pattern_ceilings.setdefault(flag.pattern_id, []).append(flag.score_ceiling)

    if not pattern_trigger_count:
        return None, False

    num_models = len(results)
    majority_threshold = num_models / 2

    # 收集多数触发的 pattern 的 ceiling
    majority_ceilings = []
    minority_triggered = False

    for pid, count in pattern_trigger_count.items():
        if count >= majority_threshold:
            ceilings = pattern_ceilings.get(pid, [])
            if ceilings:
                majority_ceilings.append(min(ceilings))
        else:
            minority_triggered = True

    if majority_ceilings:
        return min(majority_ceilings), True
    elif minority_triggered:
        return None, True
    return None, False
