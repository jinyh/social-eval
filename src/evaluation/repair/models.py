"""缺口修复的数据模型。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

ResultFamily = Literal["six_dimension", "five_axis", "e2"]

SIX_DIMENSION_MODELS = (
    "deepseek-v4-pro",
    "glm-5.1",
    "kimi-k2.6",
    "qwen3.6-plus",
)
FIVE_AXIS_MODELS = ("deepseek-v4-pro", "qwen3.6-plus")


@dataclass(frozen=True, slots=True)
class RepairTarget:
    """一个权威逐篇结果目录。"""

    key: str
    dataset: str
    family: ResultFamily
    per_paper_dir: Path
    round_number: int | None = None


@dataclass(frozen=True, slots=True)
class Gap:
    """需要补测的单个模型评分槽位。"""

    target_key: str
    paper_id: int
    dimension: str
    round_number: int
    model: str
    reason: str

    @property
    def slot_key(self) -> str:
        """返回可用于 checkpoint 的稳定槽位标识。"""

        return (
            f"{self.target_key}:{self.paper_id}:{self.dimension}:"
            f"r{self.round_number}:{self.model}"
        )

