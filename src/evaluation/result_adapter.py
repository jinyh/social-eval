"""历史六维结果的只读统一视图；不改写原始 JSON。"""

from __future__ import annotations

import statistics
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.knowledge.registry import load_scoring_protocol
from src.reporting.scoring import calculate_weighted_total


def _score_map(value: Any) -> dict[str, float]:
    if not isinstance(value, Mapping):
        return {}
    return {
        str(model): float(score)
        for model, score in value.items()
        if not isinstance(score, bool)
        and isinstance(score, (int, float))
        and 0 <= score <= 100
    }


@dataclass(frozen=True, slots=True)
class NormalizedDimensionResult:
    """一个维度的两轮评分和原始响应可用性。"""

    round1_scores: dict[str, float]
    round2_scores: dict[str, float]
    round1_raw_available: dict[str, bool]
    round2_raw_available: dict[str, bool]

    @property
    def final_scores(self) -> dict[str, float]:
        return self.round2_scores or self.round1_scores


@dataclass(frozen=True, slots=True)
class NormalizedSixDimensionResult:
    """跨历史格式稳定的单篇六维结果。"""

    paper_id: int
    framework: str | None
    stored_paper_path: str | None
    resolved_paper_path: Path | None
    dimensions: dict[str, NormalizedDimensionResult]
    round2_simple_mean: float | None
    ccb_score: float | None


def resolve_paper_path(
    stored_path: str | None,
    *,
    paper_id: int,
    raw_root: Path | None,
) -> Path | None:
    """优先保留原路径；失效时按权威 paper id 在指定语料目录回退。"""

    if stored_path:
        stored = Path(stored_path)
        if stored.exists():
            return stored.resolve()
        if raw_root is not None:
            by_name = raw_root / stored.name
            if by_name.exists():
                return by_name.resolve()
    if raw_root is None or not raw_root.exists():
        return None
    prefixes = (f"{paper_id:03d}_", f"{paper_id}_")
    candidates = sorted(
        path
        for path in raw_root.iterdir()
        if path.is_file() and path.name.startswith(prefixes)
    )
    return candidates[0].resolve() if candidates else None


def _raw_availability(
    scores: Mapping[str, float], raw: Any
) -> dict[str, bool]:
    raw_map = raw if isinstance(raw, Mapping) else {}
    return {model: isinstance(raw_map.get(model), Mapping) for model in scores}


def normalize_six_dimension_result(
    payload: Mapping[str, Any],
    *,
    paper_id: int,
    raw_root: Path | None = None,
    raw_outputs_round: int = 1,
    scoring_protocol: Mapping[str, Any] | None = None,
) -> NormalizedSixDimensionResult:
    """把 legacy E2 与标准 R1/R2 结果投影为统一只读结构。"""

    raw_dimensions = payload.get("dimensions", {})
    raw_dimensions = raw_dimensions if isinstance(raw_dimensions, Mapping) else {}
    dimensions: dict[str, NormalizedDimensionResult] = {}
    final_means: dict[str, float] = {}
    for key, raw_dimension in raw_dimensions.items():
        if not isinstance(raw_dimension, Mapping):
            continue
        r1_field = (
            "model_scores"
            if "model_scores" in raw_dimension and "round1_scores" not in raw_dimension
            else "round1_scores"
        )
        r1 = _score_map(raw_dimension.get(r1_field))
        r2 = _score_map(raw_dimension.get("round2_scores"))
        shared_raw = raw_dimension.get("raw_outputs", {})
        r1_raw = shared_raw if raw_outputs_round == 1 else {}
        r2_raw = raw_dimension.get("round2_raw_outputs", {})
        if raw_outputs_round == 2 and not r2_raw:
            r2_raw = shared_raw
        normalized = NormalizedDimensionResult(
            round1_scores=r1,
            round2_scores=r2,
            round1_raw_available=_raw_availability(r1, r1_raw),
            round2_raw_available=_raw_availability(r2, r2_raw),
        )
        dimensions[str(key)] = normalized
        if normalized.final_scores:
            final_means[str(key)] = statistics.mean(normalized.final_scores.values())

    overall = payload.get("overall", {})
    overall = overall if isinstance(overall, Mapping) else {}
    simple = overall.get("round2_final_score_mean")
    round2_simple_mean = (
        float(simple)
        if not isinstance(simple, bool) and isinstance(simple, (int, float))
        else None
    )
    protocol = dict(scoring_protocol or load_scoring_protocol())
    ccb_score = (
        calculate_weighted_total(final_means, scoring_protocol=protocol)
        if final_means
        else None
    )
    stored = payload.get("paper")
    stored_path = str(stored) if stored is not None else None
    framework = payload.get("framework")
    return NormalizedSixDimensionResult(
        paper_id=paper_id,
        framework=str(framework) if framework is not None else None,
        stored_paper_path=stored_path,
        resolved_paper_path=resolve_paper_path(
            stored_path,
            paper_id=paper_id,
            raw_root=raw_root,
        ),
        dimensions=dimensions,
        round2_simple_mean=round2_simple_mean,
        ccb_score=ccb_score,
    )
