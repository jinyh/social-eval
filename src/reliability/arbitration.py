"""仲裁机制：当模型分歧超过阈值时引入第三方模型"""

import statistics
from typing import List

from src.knowledge.schemas import ArbitrationConfig
from src.reliability.calculator import ReliabilityReport


def needs_arbitration(
    dimension_key: str,
    report: ReliabilityReport,
    config: ArbitrationConfig | None,
) -> bool:
    """判断是否需要仲裁

    Args:
        dimension_key: 维度标识符
        report: 可靠性报告（包含 std）
        config: 仲裁配置

    Returns:
        是否需要引入仲裁模型
    """
    if not config or not config.enabled:
        return False

    for trigger in config.trigger_conditions:
        if trigger.dimension == dimension_key:
            return report.std > trigger.std_threshold

    return False


def aggregate_with_arbiter(
    scores: List[float],
    arbiter_score: float,
    strategy: str,
) -> float:
    """聚合三个模型的分数

    Args:
        scores: 初始两个模型的分数列表
        arbiter_score: 仲裁模型的分数
        strategy: 聚合策略（median/mean/weighted_mean）

    Returns:
        聚合后的分数
    """
    all_scores = scores + [arbiter_score]

    if strategy == "median":
        return statistics.median(all_scores)
    elif strategy == "mean":
        return statistics.mean(all_scores)
    elif strategy == "weighted_mean":
        # 仲裁模型权重 1.5，其他模型权重 1.0
        weights = [1.0] * len(scores) + [1.5]
        return sum(s * w for s, w in zip(all_scores, weights)) / sum(weights)
    else:
        # 默认使用均值
        return statistics.mean(all_scores)
