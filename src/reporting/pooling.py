from __future__ import annotations

import statistics


def pool_dimension_scores(
    e1_scores: dict[str, dict[str, float]] | None,
    e2_scores: dict[str, dict[str, float]] | None,
    e3_scores: dict[str, dict[str, float]] | None,
    dimension_key: str,
) -> tuple[list[float], list[str]]:
    """合并单维度多轮模型分数；E3 参数仅供历史数据读取兼容。"""

    pooled: list[float] = []
    sources: list[str] = []
    for source, scores in (("E1", e1_scores), ("E2", e2_scores), ("E3", e3_scores)):
        if scores and dimension_key in scores:
            pooled.extend(float(value) for value in scores[dimension_key].values())
            sources.append(source)
    return pooled, sources


def aggregate_pool(
    pooled: list[float], sources: list[str]
) -> tuple[float | None, str | None, int | None]:
    """单源取均值，多源取中位数。"""

    if not pooled:
        return None, None, None
    if len(set(sources)) >= 2:
        return round(statistics.median(pooled), 4), "median", len(pooled)
    return round(statistics.mean(pooled), 4), "mean", len(pooled)
