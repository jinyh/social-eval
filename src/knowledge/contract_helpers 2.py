"""契约访问器：统一从 Framework 读取 v2.44/v2.45 的契约区块。

封装 `framework.xxx or framework.raw_config.get("xxx")` 的双路径读取：
- 新代码（v2.45+）读 Framework 显式字段
- 旧代码仍可通过 raw_config 访问（保留兼容）
"""

from __future__ import annotations

from typing import Any

from src.knowledge.schemas import Framework


def get_signal_config(framework: Framework) -> dict[str, Any] | None:
    """返回 autonomous_knowledge_signals 定义（v2.44+），旧框架返回 None。"""
    if framework.autonomous_knowledge_signals is not None:
        return framework.autonomous_knowledge_signals
    return framework.raw_config.get("autonomous_knowledge_signals")


def get_aggregate_contract(framework: Framework) -> dict[str, Any] | None:
    """返回 aggregate_output_contract 定义（v2.44+）。"""
    if framework.aggregate_output_contract is not None:
        return framework.aggregate_output_contract
    return framework.raw_config.get("aggregate_output_contract")


def get_review_report_contract(framework: Framework) -> dict[str, Any] | None:
    """返回 review_report 契约定义（v2.44+）。"""
    if framework.review_report is not None:
        return framework.review_report
    return framework.raw_config.get("review_report")


def get_scoring_protocol(framework: Framework) -> dict[str, Any] | None:
    """返回 scoring_protocol 定义（v2.42+）。"""
    return framework.raw_config.get("scoring_protocol")


def get_contradiction_triggers(framework: Framework) -> list[dict[str, Any]]:
    """返回 autonomous_knowledge_signals.contradiction_triggers 列表。"""
    config = get_signal_config(framework)
    if config is None:
        return []
    return list(config.get("contradiction_triggers", []) or [])


def is_full_pipeline_framework(framework: Framework) -> bool:
    """判断框架是否启用完整四阶段管线（预检 → 六维 → 信号校验 → 聚合）。

    判定依据：是否声明 autonomous_knowledge_signals 区块。
    v2.45+ 返回 True；v2.0/v2.8/v2.42/v2.43 返回 False。
    v2.44 虽有 YAML 定义但在 v2.45 之前代码不消费——v2.44 也返回 True，
    但调用方需自行决定是否启用第 3 阶段（历史上 v2.44 的定位是 spec-aligned）。
    """
    return get_signal_config(framework) is not None
