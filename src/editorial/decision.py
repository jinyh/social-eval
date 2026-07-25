from __future__ import annotations

from dataclasses import dataclass

from src.editorial.policy import EditorialPolicy

BAND_RANK = {
    "unacceptable": 0,
    "marginal": 1,
    "good": 2,
    "excellent": 3,
}


@dataclass(frozen=True)
class Recommendation:
    """内部候选类别与向编辑展示的门禁状态。"""

    candidate_decision: str
    state: str
    withheld_reasons: tuple[str, ...]


def band_for_score(score: float, policy: EditorialPolicy) -> str:
    """仅为没有结构化 band 的历史结果提供配置化回退。"""

    ordered = sorted(
        policy.band_fallback.items(),
        key=lambda item: float(item[1]["min_score"]),
        reverse=True,
    )
    for band, config in ordered:
        if score >= float(config["min_score"]):
            return band
    raise ValueError("编辑策略缺少完整的分档回退规则")


def _at_least(bands: dict[str, str], dimensions: list[str], minimum: str) -> bool:
    minimum_rank = BAND_RANK[minimum]
    return all(
        BAND_RANK.get(bands.get(key, ""), -1) >= minimum_rank for key in dimensions
    )


def calculate_candidate_decision(
    bands: dict[str, str],
    policy: EditorialPolicy,
    *,
    confirmed_gate_failure: bool = False,
) -> str:
    """按版本化期刊映射计算候选类别，不读取五轴或 CCB。"""

    mapping = policy.decision_mapping
    if confirmed_gate_failure:
        return mapping["confirmed_gate_failure"]

    defect = mapping["defect_rule"]
    if any(bands.get(key) == defect["band"] for key in defect["dimensions"]):
        return defect["decision"]

    direct = mapping["direct_accept_rule"]
    required_ok = all(
        bands.get(key) == band for key, band in direct["required_bands"].items()
    )
    excellent_count = sum(
        bands.get(key) == "excellent" for key in direct["core_dimensions"]
    )
    if (
        _at_least(bands, direct["dimensions"], direct["all_dimensions_min_band"])
        and required_ok
        and excellent_count >= int(direct["core_excellent_min_count"])
    ):
        return direct["decision"]

    minor = mapping["minor_accept_rule"]
    if _at_least(bands, minor["dimensions"], minor["min_band"]):
        return minor["decision"]
    return mapping["fallback_decision"]


def build_recommendation(
    bands: dict[str, str],
    policy: EditorialPolicy,
    *,
    rollout_state: str,
    requires_expert_review: bool = False,
    degraded: bool = False,
    pending_confirmation: bool = False,
    confirmed_gate_failure: bool = False,
) -> Recommendation:
    """计算候选类别后独立应用 shadow、专家和降级门禁。"""

    reasons: list[str] = []
    if rollout_state != "active":
        reasons.append("editorial_unit_shadow")
    if requires_expert_review:
        reasons.append("expert_review_required")
    if degraded:
        reasons.append("required_stage_degraded")
    if pending_confirmation:
        reasons.append("editor_confirmation_required")
    return Recommendation(
        candidate_decision=calculate_candidate_decision(
            bands,
            policy,
            confirmed_gate_failure=confirmed_gate_failure,
        ),
        state="withheld" if reasons else "ready",
        withheld_reasons=tuple(reasons),
    )
