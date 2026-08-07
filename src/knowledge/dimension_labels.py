from __future__ import annotations

from src.knowledge.loader import load_framework
from src.knowledge.registry import resolve_framework_path

# 六维维度标签的唯一真源：从 `law-v2.56.6-20260522.yaml` 的 dimensions 块派生，
# 不在业务代码中重复维护维度 key 与中文标签的映射。
_FRAMEWORK_PATH = resolve_framework_path("six_dimension_default")


def _load_dimension_labels() -> dict[str, str]:
    dimensions = load_framework(_FRAMEWORK_PATH).raw_config.get("dimensions") or []
    return {str(d["key"]): str(d["name_zh"]) for d in dimensions}


DIMENSION_LABELS = _load_dimension_labels()

# 兼容历史 per-paper 结果中的旧字段名；映射到当前维度 key，中文标签同样从
# DIMENSION_LABELS 派生，避免副本漂移。
_LEGACY_ALIAS_TO_KEY = {
    "research_innovation": "problem_originality",
    "problem_situation_insight": "literature_insight",
    "theoretical_construction": "analytical_framework",
    "scholarly_consensus": "conclusion_consensus",
}
LEGACY_DIMENSION_ALIASES = {
    alias: DIMENSION_LABELS[key] for alias, key in _LEGACY_ALIAS_TO_KEY.items()
}


def label_for(dimension_key: str) -> str:
    """按维度 key 返回中文标签，兼容旧字段名；未命中则原样返回。"""

    return DIMENSION_LABELS.get(dimension_key) or LEGACY_DIMENSION_ALIASES.get(
        dimension_key, dimension_key
    )
