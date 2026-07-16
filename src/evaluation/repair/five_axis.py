"""五轴位置归属度结果的语义缺口修复。"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from src.evaluation.position.workflow import (
    AXIS_KEYS,
    aggregate_final_assessment,
    decide_round2_policy,
    merge_paper_result,
    normalize_assessment,
)
from src.evaluation.repair.models import FIVE_AXIS_MODELS, Gap, RepairTarget


def is_valid_position_output(output: Any) -> bool:
    """判断模型输出是否含五个合法轴分且没有错误。"""

    if not isinstance(output, Mapping) or "error" in output:
        return False
    axes = output.get("axis_scores")
    if not isinstance(axes, Mapping):
        return False
    for axis in AXIS_KEYS:
        payload = axes.get(axis)
        score = payload.get("score") if isinstance(payload, Mapping) else None
        if isinstance(score, bool) or not isinstance(score, (int, float)) or not 0 <= score <= 2:
            return False
    return True


def scan_five_axis_gaps(
    target: RepairTarget,
    paper_id: int,
    result: Mapping[str, Any],
) -> list[Gap]:
    """扫描五轴 R1，以及已触发的 light/full R2。"""

    if target.family != "five_axis":
        raise ValueError(f"目标不是五轴：{target.key}")
    gaps: list[Gap] = []
    round1 = result.get("round1")
    r1_models = round1.get("models", {}) if isinstance(round1, Mapping) else {}
    for model in FIVE_AXIS_MODELS:
        output = r1_models.get(model) if isinstance(r1_models, Mapping) else None
        if is_valid_position_output(output):
            continue
        reason = "error_output" if isinstance(output, Mapping) and "error" in output else "invalid_output"
        gaps.append(
            Gap(
                target_key=target.key,
                paper_id=paper_id,
                dimension="position_assessment",
                round_number=1,
                model=model,
                reason=reason,
            )
        )

    mode = result.get("round2_mode")
    round2 = result.get("round2")
    if mode in {"light", "full"}:
        r2_models = round2.get("models", {}) if isinstance(round2, Mapping) else {}
        for model in FIVE_AXIS_MODELS:
            output = r2_models.get(model) if isinstance(r2_models, Mapping) else None
            if is_valid_position_output(output):
                continue
            reason = (
                "error_output"
                if isinstance(output, Mapping) and "error" in output
                else "invalid_output"
            )
            gaps.append(
                Gap(
                    target_key=target.key,
                    paper_id=paper_id,
                    dimension="position_assessment",
                    round_number=2,
                    model=model,
                    reason=reason,
                )
            )
    return gaps


def merge_five_axis_response(
    result: Mapping[str, Any],
    gap: Gap,
    response: Mapping[str, Any],
    *,
    elapsed_seconds: float,
) -> dict[str, Any]:
    """把单个五轴模型响应合入 R1 或 R2 副本。"""

    if not is_valid_position_output(response):
        raise ValueError(f"五轴响应不完整：{gap.slot_key}")
    merged = copy.deepcopy(dict(result))
    round_key = "round1" if gap.round_number == 1 else "round2"
    round_result = merged.get(round_key)
    if not isinstance(round_result, dict):
        round_result = {
            "paper_id": gap.paper_id,
            "paper": merged.get("paper", ""),
            "round2_mode": merged.get("round2_mode", "full"),
            "round2_policy": merged.get("round2_policy"),
            "models": {},
        }
        merged[round_key] = round_result
    models = round_result.setdefault("models", {})
    if is_valid_position_output(models.get(gap.model)):
        raise ValueError(f"拒绝覆盖已有有效五轴输出：{gap.slot_key}")
    normalized = normalize_assessment(dict(response))
    normalized["elapsed_seconds"] = round(elapsed_seconds, 3)
    models[gap.model] = normalized
    valid = {
        model: output
        for model, output in models.items()
        if is_valid_position_output(output)
    }
    if valid:
        round_result["aggregate_preview"] = aggregate_final_assessment(valid)
    merged.setdefault("repair_provenance", []).append(
        {
            "slot_key": gap.slot_key,
            "reason": gap.reason,
            "elapsed_seconds": round(elapsed_seconds, 3),
        }
    )
    return merged


def build_skip_round2(result: Mapping[str, Any]) -> dict[str, Any]:
    """R1 达成一致时构造显式 skip marker。"""

    merged = copy.deepcopy(dict(result))
    round1 = merged.get("round1")
    if not isinstance(round1, dict):
        raise ValueError("五轴结果缺少 R1")
    policy = decide_round2_policy(round1)
    if policy.get("mode") != "skip":
        raise ValueError(f"当前 R1 不能 skip：{policy.get('reason')}")
    r1_models = round1.get("models", {})
    round2 = {
        "paper_id": merged.get("paper_id"),
        "paper": merged.get("paper", ""),
        "round2_mode": "skip",
        "round2_policy": policy,
        "skipped": True,
        "source_round": "round1",
        "node_retrieval_candidates": round1.get("node_retrieval_candidates", []),
        "models": copy.deepcopy(r1_models),
        "aggregate_preview": aggregate_final_assessment(r1_models),
    }
    merged["round2_mode"] = "skip"
    merged["round2_policy"] = policy
    merged["round2"] = round2
    return merged


def rebuild_five_axis_record(result: Mapping[str, Any]) -> dict[str, Any]:
    """用权威 workflow 重建 merged/final，同时保留修复 provenance。"""

    paper_id = int(result.get("paper_id", 0))
    paper = Path(str(result.get("paper", "")))
    rebuilt = merge_paper_result(
        paper_id,
        paper,
        copy.deepcopy(result.get("round1")),
        copy.deepcopy(result.get("round2")),
    )
    if "repair_provenance" in result:
        rebuilt["repair_provenance"] = copy.deepcopy(result["repair_provenance"])
    return rebuilt

