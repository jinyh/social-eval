#!/usr/bin/env python3
"""Top101 中国法学自主知识体系位置归属度两轮评估。

评估口径来自：
docs/evaluation/autonomous-knowledge-system-position-assessment-v0.2.md

默认流程：
- Round 1：deepseek-v4-pro / qwen3.6-plus 独立五轴评估
- Round 2：默认按 R1 分歧条件触发；完全一致则跳过，路径/节点差异轻量复核，
  轴分/低置信/复核标记差异完整复核
- Final：逐轴保守聚合，严重分歧不取均值，保留 score_range 与复核标记

用法：
    python scripts/evaluate_top101_position_assessment_two_rounds.py
    python scripts/evaluate_top101_position_assessment_two_rounds.py --dry-run --pid 1510
    python scripts/evaluate_top101_position_assessment_two_rounds.py --round 1
    python scripts/evaluate_top101_position_assessment_two_rounds.py --round 2
    python scripts/evaluate_top101_position_assessment_two_rounds.py --r2-policy all
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import glob
import json
import logging
import statistics
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.knowledge.candidate_validation import (  # noqa: E402
    validate_candidate_nodes,
    validate_node_matches,
)
from src.knowledge.law_ontology import (  # noqa: E402
    LawOntology,
    load_law_ontology,
    parse_law_tree_markdown,
    write_law_ontology,
)
from src.knowledge.node_retrieval import RetrievedNode, retrieve_nodes  # noqa: E402

RANKING_PATH = Path("results/top101/ranking.json")
METADATA_PATH = Path("results/merged-metadata.csv")
KNOWLEDGE_PATH = Path("knowledge/中国法学自主知识体系-树状知识库.md")
ONTOLOGY_PATH = Path("knowledge/law_ontology.json")
OUTPUT_DIR = Path("results/top101-position-assessment")

MODELS = ["deepseek-v4-pro", "qwen3.6-plus"]
CONCURRENT_PAPERS = 5
MAX_TEXT_CHARS = 50_000
MAX_KNOWLEDGE_CHARS = 45_000

ROUTE_VALUES = (
    "chinese_doctrinal",
    "china_practice_governance",
    "comparative_localization",
    "chinese_legal_theory",
    "traditional_resource_transform",
    "interdisciplinary_china_data",
    "weakly_related",
)

AXIS_KEYS = (
    "object_belonging",
    "material_belonging",
    "category_autonomy",
    "explanatory_orientation",
    "system_mappability",
)

SEVERE_DISPUTE_AXES = {"category_autonomy", "system_mappability"}
ROUND2_MODES = {"skip", "light", "full"}
ROUND2_POLICIES = {"auto", "all", "skip"}
SYSTEM_ROOTS = (
    "法理学",
    "宪法学",
    "行政法学",
    "刑法学",
    "民法学",
    "商法学",
    "经济法学",
    "社会法学",
    "诉讼法学",
    "国际法学",
    "环境资源法学",
    "知识产权法学",
    "数字法学",
    "党内法规",
)

logger = logging.getLogger("top101-position-assessment")


def setup_logging(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    log_file = output_dir / "execution.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )


def strength_for_score(score: int | float) -> str:
    """Return strength band for 0-10 position-assessment score."""

    if score >= 8:
        return "strong"
    if score >= 5:
        return "medium"
    if score >= 2:
        return "weak"
    return "absent"


def _clamp_axis_score(value: Any) -> int:
    try:
        score = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, min(2, score))


def _axis_payload(raw_axis: Any, score: int) -> dict[str, Any]:
    payload = raw_axis if isinstance(raw_axis, dict) else {}
    evidence = payload.get("evidence_quotes", [])
    if not isinstance(evidence, list):
        evidence = []

    normalized = {
        "score": score,
        "evidence_quotes": evidence,
        "rationale": str(payload.get("rationale", "") or ""),
    }
    if "existing_nodes" in payload:
        nodes = payload.get("existing_nodes")
        normalized["existing_nodes"] = nodes if isinstance(nodes, list) else []
    if "candidate_nodes" in payload:
        nodes = payload.get("candidate_nodes")
        normalized["candidate_nodes"] = nodes if isinstance(nodes, list) else []
    for key in (
        "node_matches",
        "validated_node_matches",
        "validated_candidate_nodes",
        "node_retrieval_candidates",
    ):
        if key in payload:
            items = payload.get(key)
            normalized[key] = items if isinstance(items, list) else []
    return normalized


def normalize_assessment(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalize model output to v0.2 contract and recalculate totals."""

    axis_scores: dict[str, dict[str, Any]] = {}
    raw_axes = raw.get("axis_scores", {})
    raw_axes = raw_axes if isinstance(raw_axes, dict) else {}

    for axis in AXIS_KEYS:
        raw_axis = raw_axes.get(axis, {})
        raw_score = raw_axis.get("score") if isinstance(raw_axis, dict) else raw_axis
        score = _clamp_axis_score(raw_score)
        axis_scores[axis] = _axis_payload(raw_axis, score)

    total = sum(axis["score"] for axis in axis_scores.values())
    route = raw.get("research_route", {})
    if not isinstance(route, dict):
        route = {}
    primary = route.get("primary") or "weakly_related"
    if primary not in ROUTE_VALUES:
        primary = "weakly_related"
    secondary = route.get("secondary", [])
    if not isinstance(secondary, list):
        secondary = []

    risks = raw.get("risks", [])
    if not isinstance(risks, list):
        risks = []

    return {
        "research_route": {
            "primary": primary,
            "secondary": [r for r in secondary if isinstance(r, str)],
            "rationale": str(route.get("rationale", "") or ""),
        },
        "axis_scores": axis_scores,
        "total_score": total,
        "strength": strength_for_score(total),
        "confidence": str(raw.get("confidence", "low") or "low"),
        "risks": risks,
        "review_required": bool(raw.get("review_required", False)),
        "review_reason": str(raw.get("review_reason", "") or ""),
    }


def _model_axis_scores(
    assessments: dict[str, dict[str, Any]], axis: str
) -> dict[str, int]:
    return {
        model: _clamp_axis_score(
            assessment.get("axis_scores", {}).get(axis, {}).get("score")
        )
        for model, assessment in assessments.items()
    }


def aggregate_final_assessment(
    model_outputs: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Conservatively aggregate two-model position assessments.

    Axis aggregation is intentionally not a mean:
    - agreement: keep agreed score
    - neighboring disagreement: keep lower score, retain model_scores/range
    - severe disagreement (0 vs 2): keep lower score and require review
    """

    normalized = {
        model: normalize_assessment(output)
        for model, output in model_outputs.items()
        if isinstance(output, dict) and "error" not in output
    }
    if not normalized:
        return {
            "total_score": 0,
            "score_range": [0, 0],
            "strength": "absent",
            "agreement_level": "none",
            "disputed_axes": list(AXIS_KEYS),
            "review_required": True,
            "review_reason": "no_valid_model_outputs",
            "axis_scores": {},
            "per_model_total_scores": {},
        }

    final_axes: dict[str, dict[str, Any]] = {}
    disputed_axes: list[str] = []
    severe_axes: list[str] = []

    for axis in AXIS_KEYS:
        scores = _model_axis_scores(normalized, axis)
        values = list(scores.values())
        min_score = min(values)
        max_score = max(values)
        if max_score - min_score >= 2:
            disputed_axes.append(axis)
            severe_axes.append(axis)
        elif max_score - min_score == 1 and axis in SEVERE_DISPUTE_AXES:
            # Adjacent disagreements on the two most judgment-heavy axes are useful
            # to surface, but do not force review by themselves.
            disputed_axes.append(axis)

        evidence_quotes: list[str] = []
        for assessment in normalized.values():
            for quote in (
                assessment.get("axis_scores", {})
                .get(axis, {})
                .get("evidence_quotes", [])
            ):
                if quote not in evidence_quotes:
                    evidence_quotes.append(quote)

        final_axes[axis] = {
            "score": min_score,
            "model_scores": scores,
            "score_range": [min_score, max_score],
            "evidence_quotes": evidence_quotes[:4],
        }

        if axis == "system_mappability":
            existing_nodes: list[Any] = []
            candidate_nodes: list[Any] = []
            node_matches: list[Any] = []
            validated_node_matches: list[Any] = []
            validated_candidate_nodes: list[Any] = []
            retrieval_candidates: list[Any] = []
            for assessment in normalized.values():
                axis_payload = assessment.get("axis_scores", {}).get(axis, {})
                for node in axis_payload.get("existing_nodes", []):
                    if node not in existing_nodes:
                        existing_nodes.append(node)
                for node in axis_payload.get("candidate_nodes", []):
                    if node not in candidate_nodes:
                        candidate_nodes.append(node)
                for node in axis_payload.get("node_matches", []):
                    if node not in node_matches:
                        node_matches.append(node)
                for node in axis_payload.get("validated_node_matches", []):
                    if node not in validated_node_matches:
                        validated_node_matches.append(node)
                for node in axis_payload.get("validated_candidate_nodes", []):
                    if node not in validated_candidate_nodes:
                        validated_candidate_nodes.append(node)
                for node in axis_payload.get("node_retrieval_candidates", []):
                    if node not in retrieval_candidates:
                        retrieval_candidates.append(node)
            final_axes[axis]["existing_nodes"] = existing_nodes
            final_axes[axis]["candidate_nodes"] = candidate_nodes
            final_axes[axis]["node_matches"] = node_matches
            final_axes[axis]["validated_node_matches"] = validated_node_matches
            final_axes[axis]["validated_candidate_nodes"] = validated_candidate_nodes
            final_axes[axis]["node_retrieval_candidates"] = retrieval_candidates

    per_model_totals = {
        model: int(assessment.get("total_score", 0))
        for model, assessment in normalized.items()
    }
    total = sum(axis["score"] for axis in final_axes.values())
    score_range = [min(per_model_totals.values()), max(per_model_totals.values())]

    if severe_axes:
        agreement = "low"
    elif any(
        payload["score_range"][0] != payload["score_range"][1]
        for payload in final_axes.values()
    ):
        agreement = "medium"
    else:
        agreement = "high"

    route_counts = Counter(
        assessment.get("research_route", {}).get("primary", "weakly_related")
        for assessment in normalized.values()
    )
    primary_route = route_counts.most_common(1)[0][0]
    review_required = bool(severe_axes) or any(
        assessment.get("review_required", False) for assessment in normalized.values()
    )
    review_reasons = []
    if severe_axes:
        review_reasons.append(
            "severe_axis_disagreement:" + ",".join(sorted(severe_axes))
        )
    for assessment in normalized.values():
        reason = assessment.get("review_reason")
        if reason:
            review_reasons.append(reason)

    return {
        "research_route": {
            "primary": primary_route,
            "per_model": {
                model: assessment.get("research_route", {})
                for model, assessment in normalized.items()
            },
        },
        "axis_scores": final_axes,
        "total_score": total,
        "score_range": score_range,
        "strength": strength_for_score(total),
        "agreement_level": agreement,
        "disputed_axes": disputed_axes,
        "severe_disputed_axes": severe_axes,
        "review_required": review_required,
        "review_reason": "; ".join(review_reasons),
        "per_model_total_scores": per_model_totals,
    }


def _valid_r1_model_assessments(r1_result: dict[str, Any]) -> dict[str, dict[str, Any]]:
    models = r1_result.get("models", {})
    if not isinstance(models, dict):
        return {}
    return {
        model: normalize_assessment(output)
        for model, output in models.items()
        if isinstance(output, dict) and "error" not in output
    }


def _node_label(node: Any) -> str:
    if isinstance(node, dict):
        raw = node.get("name") or node.get("title") or node.get("node") or ""
    else:
        raw = node
    return str(raw).strip().lower()


def _system_node_labels(assessment: dict[str, Any]) -> set[str]:
    payload = assessment.get("axis_scores", {}).get("system_mappability", {})
    labels: set[str] = set()
    for key in ("existing_nodes", "candidate_nodes"):
        nodes = payload.get(key, [])
        if isinstance(nodes, list):
            labels.update(label for node in nodes if (label := _node_label(node)))
    return labels


def _system_roots(assessment: dict[str, Any]) -> set[str]:
    structured_roots = _structured_system_roots(assessment)
    if structured_roots:
        return structured_roots

    roots: set[str] = set()
    for label in _system_node_labels(assessment):
        roots.update(root for root in SYSTEM_ROOTS if root in label)
    return roots


def _structured_system_roots(assessment: dict[str, Any]) -> set[str]:
    payload = assessment.get("axis_scores", {}).get("system_mappability", {})
    roots: set[str] = set()
    for key in ("validated_node_matches", "node_matches"):
        for node in payload.get(key, []):
            if not isinstance(node, dict):
                continue
            if node.get("status") == "rejected":
                continue
            node_id = str(node.get("node_id") or node.get("matched_node_id") or "")
            if node_id:
                roots.add(node_id.split(".", 1)[0])
    for node in payload.get("validated_candidate_nodes", []):
        if not isinstance(node, dict) or node.get("status") == "rejected":
            continue
        parent_id = str(node.get("parent_node_id") or node.get("matched_node_id") or "")
        if parent_id:
            roots.add(parent_id.split(".", 1)[0])
    return roots


def _has_system_node_conflict(assessments: dict[str, dict[str, Any]]) -> bool:
    root_sets = [
        roots
        for assessment in assessments.values()
        if (roots := _system_roots(assessment))
    ]
    if len(root_sets) < 2:
        return False
    return not set.intersection(*root_sets)


def decide_round2_policy(r1_result: dict[str, Any]) -> dict[str, Any]:
    """Decide whether Round 2 is needed from Round 1 model agreement.

    Modes:
    - skip: axis scores, primary route, confidence and review flags agree enough.
    - light: scores agree, but route or system-node placement needs arbitration.
    - full: score disagreement, low confidence, review flag, or incomplete R1.
    """

    assessments = _valid_r1_model_assessments(r1_result)
    reasons: list[str] = []
    axis_disagreements: list[str] = []

    if len(assessments) < len(MODELS):
        missing = sorted(set(MODELS) - set(assessments))
        return {
            "mode": "full",
            "reason": "r1_incomplete",
            "reasons": ["r1_incomplete:" + ",".join(missing)],
            "axis_disagreements": [],
        }

    for model, assessment in assessments.items():
        if assessment.get("review_required"):
            reasons.append(f"review_required:{model}")
        if assessment.get("confidence") == "low":
            reasons.append(f"low_confidence:{model}")

    for axis in AXIS_KEYS:
        scores = {
            model: _clamp_axis_score(
                assessment.get("axis_scores", {}).get(axis, {}).get("score")
            )
            for model, assessment in assessments.items()
        }
        if len(set(scores.values())) > 1:
            axis_disagreements.append(axis)
            reasons.append(f"axis_score_disagreement:{axis}")

    if reasons:
        return {
            "mode": "full",
            "reason": "full_review_required",
            "reasons": reasons,
            "axis_disagreements": axis_disagreements,
        }

    primary_routes = {
        assessment.get("research_route", {}).get("primary", "weakly_related")
        for assessment in assessments.values()
    }
    if len(primary_routes) > 1:
        reasons.append("route_primary_disagreement")

    if _has_system_node_conflict(assessments):
        reasons.append("system_node_conflict")

    if reasons:
        return {
            "mode": "light",
            "reason": "route_or_node_arbitration",
            "reasons": reasons,
            "axis_disagreements": [],
        }

    return {
        "mode": "skip",
        "reason": "r1_full_agreement",
        "reasons": [],
        "axis_disagreements": [],
    }


def enforce_light_round2_axis_agreement(
    output: dict[str, Any],
    *,
    r1_result: dict[str, Any],
    model_name: str,
) -> dict[str, Any]:
    """Keep agreed R1 axis scores stable during light Round 2.

    Light R2 is only for route or system-node arbitration. If both R1 models
    agreed on an axis score, light R2 must not turn that into a score dispute.
    """

    if not isinstance(output, dict) or "error" in output:
        return output

    corrected = normalize_assessment(output)
    r1_assessments = _valid_r1_model_assessments(r1_result)
    if not r1_assessments:
        return corrected

    self_r1 = r1_assessments.get(model_name)
    overrides: dict[str, dict[str, int]] = {}
    for axis in AXIS_KEYS:
        r1_scores = [
            _clamp_axis_score(
                assessment.get("axis_scores", {}).get(axis, {}).get("score")
            )
            for assessment in r1_assessments.values()
        ]
        if len(set(r1_scores)) != 1:
            continue

        agreed_score = r1_scores[0]
        axis_payload = corrected["axis_scores"][axis]
        current_score = _clamp_axis_score(axis_payload.get("score"))
        if current_score == agreed_score:
            continue

        overrides[axis] = {"from": current_score, "to": agreed_score}
        axis_payload["score"] = agreed_score

        # If the light output discarded evidence for a non-node axis, restore
        # the model's original agreed R1 payload. For system_mappability, keep
        # light R2 node arbitration fields but preserve the agreed score.
        if axis != "system_mappability" and self_r1:
            r1_payload = self_r1.get("axis_scores", {}).get(axis, {})
            axis_payload["evidence_quotes"] = list(
                r1_payload.get("evidence_quotes", [])
            )
            axis_payload["rationale"] = str(r1_payload.get("rationale", "") or "")
        elif axis == "system_mappability" and self_r1:
            r1_payload = self_r1.get("axis_scores", {}).get(axis, {})
            for key in (
                "node_matches",
                "existing_nodes",
                "candidate_nodes",
                "validated_node_matches",
                "validated_candidate_nodes",
                "node_retrieval_candidates",
            ):
                if not axis_payload.get(key) and r1_payload.get(key):
                    axis_payload[key] = list(r1_payload.get(key, []))

    if overrides:
        corrected["light_round2_score_overrides"] = overrides
        corrected["total_score"] = sum(
            axis_payload["score"]
            for axis_payload in corrected["axis_scores"].values()
        )
        corrected["strength"] = strength_for_score(corrected["total_score"])
    return corrected


def load_top101(path: Path = RANKING_PATH) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data["papers"]


def load_metadata(path: Path = METADATA_PATH) -> dict[int, dict[str, str]]:
    metadata: dict[int, dict[str, str]] = {}
    with path.open("r", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            metadata[int(row["编号"])] = row
    return metadata


def load_knowledge_excerpt(path: Path, max_chars: int) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")[:max_chars]


def load_or_build_ontology(
    markdown_path: Path,
    ontology_path: Path,
    *,
    rebuild: bool = False,
) -> LawOntology:
    if ontology_path.exists() and not rebuild:
        return load_law_ontology(ontology_path)
    text = markdown_path.read_text(encoding="utf-8")
    ontology = parse_law_tree_markdown(text, source_path=str(markdown_path))
    write_law_ontology(ontology, ontology_path)
    return ontology


def find_pdf(pid: int, paper_dir: Path) -> Path | None:
    matches = sorted(glob.glob(str(paper_dir / f"{pid:04d}-*.pdf")))
    return Path(matches[0]) if matches else None


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n……（文本已截断）"


def query_text_for_retrieval(paper_meta: dict[str, Any], paper_text: str) -> str:
    fields = [
        paper_meta.get("题目") or paper_meta.get("title") or "",
        paper_meta.get("主题词") or paper_meta.get("keywords") or "",
        paper_meta.get("专家审阅学科") or paper_meta.get("discipline") or "",
        paper_meta.get("分类") or paper_meta.get("category") or "",
        paper_meta.get("分类-Q") or "",
        paper_text[:8000],
    ]
    return "\n".join(str(field) for field in fields if field)


def discipline_hint_from_meta(paper_meta: dict[str, Any]) -> str:
    return str(
        paper_meta.get("专家审阅学科")
        or paper_meta.get("discipline")
        or paper_meta.get("分类")
        or paper_meta.get("category")
        or paper_meta.get("分类-Q")
        or ""
    )


def format_retrieved_nodes_for_prompt(nodes: list[RetrievedNode]) -> str:
    if not nodes:
        return "（未检索到候选节点；如确有知识产出，可提出候选新增节点，但必须给出父节点和原文证据。）"
    lines = []
    for index, node in enumerate(nodes, start=1):
        methods = "+".join(node.match_methods)
        lines.append(
            f"{index}. [{node.node_id}] {node.path} "
            f"({node.node_type}, score={node.score:.2f}, methods={methods})"
        )
    return "\n".join(lines)


def retrieved_nodes_from_result(result: dict[str, Any]) -> list[RetrievedNode]:
    raw_nodes = result.get("node_retrieval_candidates", [])
    if not isinstance(raw_nodes, list):
        return []
    nodes: list[RetrievedNode] = []
    for raw in raw_nodes:
        if not isinstance(raw, dict):
            continue
        try:
            nodes.append(
                RetrievedNode(
                    node_id=str(raw.get("node_id", "")),
                    label=str(raw.get("label", "")),
                    path=str(raw.get("path", "")),
                    node_type=str(raw.get("node_type", "")),
                    score=float(raw.get("score", 0) or 0),
                    match_methods=[
                        str(item) for item in raw.get("match_methods", []) if item
                    ],
                )
            )
        except (TypeError, ValueError):
            continue
    return nodes


def apply_node_validation_to_assessment(
    output: dict[str, Any],
    *,
    ontology: LawOntology,
    retrieved_nodes: list[RetrievedNode],
    paper_title: str,
    paper_text: str,
) -> dict[str, Any]:
    if not isinstance(output, dict) or "error" in output:
        return output

    assessment = normalize_assessment(output)
    system_axis = assessment["axis_scores"]["system_mappability"]
    raw_matches: list[Any] = []
    for key in ("node_matches", "existing_nodes"):
        value = system_axis.get(key, [])
        if isinstance(value, list):
            raw_matches.extend(value)

    raw_candidates = system_axis.get("candidate_nodes", [])

    validated_matches = validate_node_matches(
        raw_matches,
        ontology=ontology,
        retrieved_nodes=retrieved_nodes,
    )
    validated_candidates = validate_candidate_nodes(
        raw_candidates if isinstance(raw_candidates, list) else [],
        ontology=ontology,
        retrieved_nodes=retrieved_nodes,
        paper_title=paper_title,
        paper_text=paper_text,
    )

    system_axis["validated_node_matches"] = [
        item.to_dict() for item in validated_matches
    ]
    system_axis["validated_candidate_nodes"] = [
        item.to_dict() for item in validated_candidates
    ]
    system_axis["node_retrieval_candidates"] = [
        item.to_dict() for item in retrieved_nodes
    ]

    accepted_match = any(item.status == "accepted" for item in validated_matches)
    accepted_candidate = any(
        item.status == "accepted"
        and item.match_type
        in {"existing_node_match", "extension_node", "cross_node", "candidate_new_node"}
        for item in validated_candidates
    )
    needs_review = any(
        item.status == "needs_review"
        for item in [*validated_matches, *validated_candidates]
    )
    if system_axis["score"] >= 2 and not (accepted_match or accepted_candidate):
        system_axis["score"] = 1 if needs_review else 0
        assessment["review_required"] = True
        reason = "system_mappability_node_validation"
        existing_reason = assessment.get("review_reason", "")
        assessment["review_reason"] = (
            f"{existing_reason}; {reason}" if existing_reason else reason
        )

    assessment["total_score"] = sum(
        axis_payload["score"] for axis_payload in assessment["axis_scores"].values()
    )
    assessment["strength"] = strength_for_score(assessment["total_score"])
    return assessment


def build_round1_prompt(
    paper_meta: dict[str, Any],
    paper_text: str,
    knowledge_excerpt: str,
    max_text_chars: int = MAX_TEXT_CHARS,
    node_candidates_text: str | None = None,
) -> str:
    title = paper_meta.get("题目") or paper_meta.get("title") or ""
    journal = paper_meta.get("期刊") or paper_meta.get("journal") or ""
    year = paper_meta.get("年份") or paper_meta.get("year") or ""
    discipline = paper_meta.get("专家审阅学科") or paper_meta.get("discipline") or ""
    route_enum = "/".join(ROUTE_VALUES)

    return f"""你是一位法学知识体系分析专家。请对论文进行【中国法学自主知识体系位置归属度评价】。

重要边界：
- 不评价论文质量、原创性强弱、论证是否成功；这些属于六维学术质量评价。
- 只评价论文产出的知识单元能否被纳入中国法学自主知识体系的位置结构。
- 位置结构包括：学科位置、知识类型位置、既有知识树节点、细化节点、交叉节点或候选新增节点。
- 本评价不是“信号校验”，而是结构化 assessment。

评分量尺：
- 五轴各 0-2 分，总分 0-10。
- 0=无明确证据或只是背景性提及。
- 1=有局部证据，但不是论文核心结构。
- 2=构成论文核心问题、核心材料、核心范畴、核心解释目标或明确体系位置。
- uncertain 不给 1 分；证据不足时给 0 并降低 confidence。

五轴：
1. object_belonging：对象归属度。论文核心问题是否属于中国法秩序、中国制度、中国司法/治理实践、中国法学争论或中国法律传统。
2. material_belonging：材料归属度。核心材料是否来自中国规范、判例、政策制度、法律史料、实务材料、中文法学争论或中国经验数据。
3. category_autonomy：范畴自主度。核心分析范畴是否经过中国法语境重置。
4. explanatory_orientation：解释目标归属度。最终解释目标是否指向中国法学知识生产。
5. system_mappability：体系映射度。知识产出能否映射到既有节点、细化节点、交叉节点或候选新增节点。

防饱和规则：
- 不得因为“论文讨论中国法”就自动五轴高分。
- 常规中国法条解释不能自动推出 category_autonomy=2 或 system_mappability=2。
- category_autonomy=2 必须说明核心范畴如何由中国制度、实践、传统、法学争论或语境转换生成。
- system_mappability=2 必须给出明确既有节点、细化节点、交叉节点或候选新增节点。
- 候选新增节点必须可命名、可复述、可放入知识树；不能直接把论文题目当作节点。

研究路径 primary 只能取一个：
{", ".join(ROUTE_VALUES)}

论文信息：
- 题目：{title}
- 期刊：{journal}
- 年份：{year}
- 专家审阅学科：{discipline}

候选知识体系节点：
{node_candidates_text if node_candidates_text is not None else knowledge_excerpt or "（未提供候选节点；请只根据论文文本判断候选节点）"}

论文正文：
{_truncate(paper_text, max_text_chars)}

请只输出 JSON，不要输出 Markdown 代码块或额外说明。结构如下：
{{
  "research_route": {{
    "primary": "{route_enum}",
    "secondary": [],
    "rationale": "路径判断理由，80字以内"
  }},
  "axis_scores": {{
    "object_belonging": {{"score": 0, "evidence_quotes": [], "rationale": ""}},
    "material_belonging": {{"score": 0, "evidence_quotes": [], "rationale": ""}},
    "category_autonomy": {{"score": 0, "evidence_quotes": [], "rationale": ""}},
    "explanatory_orientation": {{"score": 0, "evidence_quotes": [], "rationale": ""}},
    "system_mappability": {{
      "score": 0,
      "node_matches": [
        {{
          "node_id": "只能从候选节点中选择，若无则留空",
          "label": "候选节点标签",
          "match_type": "existing_node",
          "evidence_quote": "论文原文证据",
          "rationale": "匹配理由"
        }}
      ],
      "existing_nodes": [],
      "candidate_nodes": [
        {{
          "label": "候选新增节点名",
          "match_type": "extension_node/cross_node/candidate_new_node",
          "parent_node_id": "候选父节点 node_id",
          "evidence_quote": "论文原文证据",
          "rationale": "为什么可作为候选节点"
        }}
      ],
      "evidence_quotes": [],
      "rationale": ""
    }}
  }},
  "total_score": 0,
  "strength": "strong/medium/weak/absent",
  "confidence": "high/medium/low",
  "risks": [],
  "review_required": false,
  "review_reason": ""
}}
"""


def _format_model_assessment(label: str, output: dict[str, Any]) -> str:
    if "error" in output:
        return f"【{label}】调用失败：{output.get('error')}"
    normalized = normalize_assessment(output)
    lines = [
        f"【{label}】",
        f"研究路径：{normalized['research_route']['primary']}",
        f"总分：{normalized['total_score']}/10（{normalized['strength']}）",
    ]
    for axis in AXIS_KEYS:
        payload = normalized["axis_scores"][axis]
        quotes = "；".join(str(q)[:60] for q in payload.get("evidence_quotes", [])[:2])
        lines.append(
            f"- {axis}: {payload['score']}，理由：{payload.get('rationale', '')}，"
            f"证据：{quotes or '无'}"
        )
    return "\n".join(lines)


def build_round2_prompt(
    paper_meta: dict[str, Any],
    paper_text: str,
    knowledge_excerpt: str,
    self_r1_output: dict[str, Any],
    other_r1_output: dict[str, Any],
    model_name: str,
    other_model_name: str,
    max_text_chars: int = MAX_TEXT_CHARS,
    node_candidates_text: str | None = None,
) -> str:
    self_text = _format_model_assessment(
        f"你的第一轮评价（{model_name}）", self_r1_output
    )
    other_text = _format_model_assessment(
        f"另一模型的第一轮评价（{other_model_name}）", other_r1_output
    )
    base_prompt = build_round1_prompt(
        paper_meta=paper_meta,
        paper_text=paper_text,
        knowledge_excerpt=knowledge_excerpt,
        max_text_chars=max_text_chars,
        node_candidates_text=node_candidates_text,
    )
    return f"""{base_prompt}

---

交叉评审补充任务：

你现在进入 Round 2。请参考以下两份 Round 1 评价，重新检查五轴分数和证据。

{self_text}

---

{other_text}

请重点判断：
1. 对方是否提出了你遗漏的有效证据。
2. 你是否把论文质量/创新性误当成位置归属度。
3. category_autonomy 和 system_mappability 是否有足够证据支撑高分。
4. 若不同意对方判断，请在 rejected_points 中说明理由。

请仍然只输出 JSON，并额外包含：
{{
  "score_changed": true,
  "change_details": "≤200字",
  "accepted_points": [],
  "rejected_points": []
}}
"""


def build_light_round2_prompt(
    paper_meta: dict[str, Any],
    knowledge_excerpt: str,
    self_r1_output: dict[str, Any],
    other_r1_output: dict[str, Any],
    model_name: str,
    other_model_name: str,
    node_candidates_text: str | None = None,
) -> str:
    title = paper_meta.get("题目") or paper_meta.get("title") or ""
    journal = paper_meta.get("期刊") or paper_meta.get("journal") or ""
    year = paper_meta.get("年份") or paper_meta.get("year") or ""
    self_text = _format_model_assessment(
        f"你的第一轮评价（{model_name}）", self_r1_output
    )
    other_text = _format_model_assessment(
        f"另一模型的第一轮评价（{other_model_name}）", other_r1_output
    )

    return f"""你是一位法学知识体系分析专家。现在进行【轻量 Round 2】。

轻量 Round 2 只用于处理 Round 1 中的研究路径或体系节点归属差异。
不要重新评价论文质量、原创性强弱或六维度学术质量。
如果两模型五轴分数一致，原则上保留五轴分数；只有当路径/节点差异暴露出明显归属错误时才调整相关轴分，并说明理由。

论文信息：
- 题目：{title}
- 期刊：{journal}
- 年份：{year}

候选知识体系节点：
{node_candidates_text if node_candidates_text is not None else knowledge_excerpt or "（未提供候选节点；请只根据 Round 1 证据判断候选节点）"}

Round 1 评价：
{self_text}

---

{other_text}

请重点裁定：
1. research_route.primary 应采用哪一路径，是否需要 secondary。
2. system_mappability 的 node_matches / candidate_nodes 是否可合并、修正或新增。
3. 若五轴分数保持不变，请沿用 Round 1 分数并重新输出完整 JSON。

请只输出 JSON，不要输出 Markdown 代码块或额外说明。结构如下：
{{
  "research_route": {{
    "primary": "只能从既定 route 枚举中选一个",
    "secondary": [],
    "rationale": "路径裁定理由，80字以内"
  }},
  "axis_scores": {{
    "object_belonging": {{"score": 0, "evidence_quotes": [], "rationale": ""}},
    "material_belonging": {{"score": 0, "evidence_quotes": [], "rationale": ""}},
    "category_autonomy": {{"score": 0, "evidence_quotes": [], "rationale": ""}},
    "explanatory_orientation": {{"score": 0, "evidence_quotes": [], "rationale": ""}},
    "system_mappability": {{
      "score": 0,
      "node_matches": [],
      "existing_nodes": [],
      "candidate_nodes": [],
      "evidence_quotes": [],
      "rationale": ""
    }}
  }},
  "total_score": 0,
  "strength": "strong/medium/weak/absent",
  "confidence": "high/medium/low",
  "risks": [],
  "review_required": false,
  "review_reason": "",
  "score_changed": false,
  "change_details": "≤200字",
  "accepted_points": [],
  "rejected_points": []
}}
"""


async def call_model(
    model_name: str,
    prompt: str,
    provider_map: dict[str, Any],
) -> dict[str, Any]:
    provider = provider_map.get(model_name)
    if provider is None:
        return {"error": f"Provider {model_name} 未找到", "model": model_name}
    start = time.time()
    try:
        result = await provider.generate_json_response(prompt)
        normalized = normalize_assessment(result)
        for key in (
            "score_changed",
            "change_details",
            "accepted_points",
            "rejected_points",
        ):
            if key in result:
                normalized[key] = result[key]
        normalized["elapsed_seconds"] = round(time.time() - start, 1)
        return normalized
    except Exception as exc:  # noqa: BLE001
        logger.error("模型 %s 调用失败：%s", model_name, exc)
        return {
            "error": str(exc),
            "model": model_name,
            "elapsed_seconds": round(time.time() - start, 1),
        }


def parse_pdf_text(pdf_path: Path) -> str:
    from src.ingestion.parsers.pdf_parser import PDFParser

    parsed = PDFParser().parse(str(pdf_path))
    return parsed.text


async def run_round1_paper(
    pid: int,
    pdf_path: Path,
    paper_meta: dict[str, Any],
    ontology: LawOntology,
    provider_map: dict[str, Any],
    output_dir: Path,
    semaphore: asyncio.Semaphore,
    max_text_chars: int,
    node_top_k: int,
) -> dict[str, Any] | None:
    output_path = output_dir / f"paper-{pid}.json"
    if output_path.exists():
        logger.info("[R1] PID=%s 跳过（已存在）", pid)
        return json.loads(output_path.read_text(encoding="utf-8"))

    async with semaphore:
        logger.info("[R1] PID=%s %s 开始", pid, pdf_path.name[:60])
        start = time.time()
        try:
            paper_text = parse_pdf_text(pdf_path)
        except Exception as exc:  # noqa: BLE001
            logger.error("[R1] PID=%s PDF 解析失败：%s", pid, exc)
            return None
        if not paper_text.strip():
            logger.error("[R1] PID=%s 文本为空", pid)
            return None

        retrieved_nodes = retrieve_nodes(
            query_text_for_retrieval(paper_meta, paper_text),
            ontology,
            discipline_hint=discipline_hint_from_meta(paper_meta),
            top_k=node_top_k,
        )
        node_candidates_text = format_retrieved_nodes_for_prompt(retrieved_nodes)
        prompt = build_round1_prompt(
            paper_meta=paper_meta,
            paper_text=paper_text,
            knowledge_excerpt="",
            max_text_chars=max_text_chars,
            node_candidates_text=node_candidates_text,
        )
        outputs = await asyncio.gather(
            *[call_model(model, prompt, provider_map) for model in MODELS]
        )
        title = str(paper_meta.get("题目") or paper_meta.get("title") or "")
        outputs = [
            apply_node_validation_to_assessment(
                output,
                ontology=ontology,
                retrieved_nodes=retrieved_nodes,
                paper_title=title,
                paper_text=paper_text,
            )
            for output in outputs
        ]
        result = {
            "paper_id": pid,
            "paper": pdf_path.name,
            "timestamp": datetime.now().isoformat(),
            "node_retrieval_candidates": [node.to_dict() for node in retrieved_nodes],
            "models": dict(zip(MODELS, outputs, strict=False)),
            "elapsed_seconds": round(time.time() - start, 1),
        }
        valid = {m: o for m, o in result["models"].items() if "error" not in o}
        if valid:
            result["aggregate_preview"] = aggregate_final_assessment(valid)
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info("[R1] PID=%s 完成", pid)
        return result


async def run_round2_paper(
    pid: int,
    pdf_path: Path,
    paper_meta: dict[str, Any],
    ontology: LawOntology,
    r1_result: dict[str, Any],
    provider_map: dict[str, Any],
    output_dir: Path,
    semaphore: asyncio.Semaphore,
    max_text_chars: int,
    policy: dict[str, Any],
    node_top_k: int,
) -> dict[str, Any] | None:
    mode = str(policy.get("mode", "full"))
    if mode not in ROUND2_MODES:
        mode = "full"

    output_path = output_dir / f"paper-{pid}.json"
    if output_path.exists():
        logger.info("[R2] PID=%s 跳过（已存在）", pid)
        return json.loads(output_path.read_text(encoding="utf-8"))

    r1_models = r1_result.get("models", {})
    if any("error" in r1_models.get(model, {"error": "missing"}) for model in MODELS):
        logger.warning("[R2] PID=%s R1 不完整，跳过", pid)
        return None

    async with semaphore:
        logger.info("[R2:%s] PID=%s %s 开始", mode, pid, pdf_path.name[:60])
        start = time.time()
        prompts = []
        paper_text = ""
        retrieved_nodes = retrieved_nodes_from_result(r1_result)
        if mode == "light":
            node_candidates_text = format_retrieved_nodes_for_prompt(retrieved_nodes)
            for index, model_name in enumerate(MODELS):
                other_model_name = MODELS[1 - index]
                prompts.append(
                    build_light_round2_prompt(
                        paper_meta=paper_meta,
                        knowledge_excerpt="",
                        self_r1_output=r1_models[model_name],
                        other_r1_output=r1_models[other_model_name],
                        model_name=model_name,
                        other_model_name=other_model_name,
                        node_candidates_text=node_candidates_text,
                    )
                )
        else:
            try:
                paper_text = parse_pdf_text(pdf_path)
            except Exception as exc:  # noqa: BLE001
                logger.error("[R2] PID=%s PDF 解析失败：%s", pid, exc)
                return None
            if not paper_text.strip():
                logger.error("[R2] PID=%s 文本为空", pid)
                return None

            retrieved_nodes = retrieve_nodes(
                query_text_for_retrieval(paper_meta, paper_text),
                ontology,
                discipline_hint=discipline_hint_from_meta(paper_meta),
                top_k=node_top_k,
            )
            node_candidates_text = format_retrieved_nodes_for_prompt(retrieved_nodes)
            for index, model_name in enumerate(MODELS):
                other_model_name = MODELS[1 - index]
                prompts.append(
                    build_round2_prompt(
                        paper_meta=paper_meta,
                        paper_text=paper_text,
                        knowledge_excerpt="",
                        self_r1_output=r1_models[model_name],
                        other_r1_output=r1_models[other_model_name],
                        model_name=model_name,
                        other_model_name=other_model_name,
                        max_text_chars=max_text_chars,
                        node_candidates_text=node_candidates_text,
                    )
                )
        outputs = await asyncio.gather(
            *[
                call_model(model_name, prompt, provider_map)
                for model_name, prompt in zip(MODELS, prompts, strict=False)
            ]
        )
        if mode == "light":
            outputs = [
                enforce_light_round2_axis_agreement(
                    output,
                    r1_result=r1_result,
                    model_name=model_name,
                )
                for model_name, output in zip(MODELS, outputs, strict=False)
            ]
        title = str(paper_meta.get("题目") or paper_meta.get("title") or "")
        validation_text = paper_text or ""
        outputs = [
            apply_node_validation_to_assessment(
                output,
                ontology=ontology,
                retrieved_nodes=retrieved_nodes,
                paper_title=title,
                paper_text=validation_text,
            )
            for output in outputs
        ]
        result = {
            "paper_id": pid,
            "paper": pdf_path.name,
            "timestamp": datetime.now().isoformat(),
            "round2_mode": mode,
            "round2_policy": policy,
            "node_retrieval_candidates": [node.to_dict() for node in retrieved_nodes],
            "models": dict(zip(MODELS, outputs, strict=False)),
            "elapsed_seconds": round(time.time() - start, 1),
        }
        valid = {m: o for m, o in result["models"].items() if "error" not in o}
        if valid:
            result["aggregate_preview"] = aggregate_final_assessment(valid)
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info("[R2] PID=%s 完成", pid)
        return result


async def write_round2_skip_marker(
    pid: int,
    pdf_path: Path,
    r1_result: dict[str, Any],
    output_dir: Path,
    policy: dict[str, Any],
) -> dict[str, Any]:
    output_path = output_dir / f"paper-{pid}.json"
    if output_path.exists():
        logger.info("[R2:skip] PID=%s 跳过（已存在）", pid)
        return json.loads(output_path.read_text(encoding="utf-8"))

    start = time.time()
    result = {
        "paper_id": pid,
        "paper": pdf_path.name,
        "timestamp": datetime.now().isoformat(),
        "round2_mode": "skip",
        "round2_policy": policy,
        "skipped": True,
        "source_round": "round1",
        "node_retrieval_candidates": r1_result.get("node_retrieval_candidates", []),
        "models": r1_result.get("models", {}),
        "elapsed_seconds": round(time.time() - start, 1),
    }
    valid = {m: o for m, o in result["models"].items() if "error" not in o}
    if valid:
        result["aggregate_preview"] = aggregate_final_assessment(valid)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info("[R2:skip] PID=%s R1 完全一致，写入跳过标记", pid)
    return result


def merge_paper_result(
    pid: int,
    pdf_path: Path,
    r1_result: dict[str, Any] | None,
    r2_result: dict[str, Any] | None,
) -> dict[str, Any]:
    source = r2_result or r1_result
    final = None
    if source:
        source_models = source.get("models", {})
        if (
            source.get("round2_mode") == "light"
            and r1_result is not None
            and isinstance(source_models, dict)
        ):
            source_models = {
                model: enforce_light_round2_axis_agreement(
                    output,
                    r1_result=r1_result,
                    model_name=model,
                )
                for model, output in source_models.items()
            }
        valid = {
            model: output
            for model, output in source_models.items()
            if isinstance(output, dict) and "error" not in output
        }
        if valid:
            final = aggregate_final_assessment(valid)
    return {
        "paper_id": pid,
        "paper": pdf_path.name,
        "models": MODELS,
        "method": "position_assessment_v0.2_two_models_conditional_round2",
        "round2_mode": (r2_result or {}).get("round2_mode", "not_run"),
        "round2_policy": (r2_result or {}).get("round2_policy"),
        "node_retrieval_candidates": (source or {}).get(
            "node_retrieval_candidates", []
        ),
        "round1": r1_result,
        "round2": r2_result,
        "final": final,
    }


def generate_summary(merged_results: list[dict[str, Any]]) -> dict[str, Any]:
    scores: list[int] = []
    strengths: Counter[str] = Counter()
    agreements: Counter[str] = Counter()
    r2_modes: Counter[str] = Counter()
    disputed_axes: Counter[str] = Counter()
    severe_axes: Counter[str] = Counter()
    review_required = 0
    completed = 0

    for result in merged_results:
        r2_modes[result.get("round2_mode", "not_run")] += 1
        final = result.get("final")
        if not final:
            continue
        completed += 1
        scores.append(int(final["total_score"]))
        strengths[final["strength"]] += 1
        agreements[final["agreement_level"]] += 1
        review_required += int(bool(final.get("review_required")))
        disputed_axes.update(final.get("disputed_axes", []))
        severe_axes.update(final.get("severe_disputed_axes", []))

    score_stats = {}
    if scores:
        score_stats = {
            "count": len(scores),
            "mean": round(statistics.mean(scores), 2),
            "min": min(scores),
            "max": max(scores),
        }
    return {
        "generated_at": datetime.now().isoformat(),
        "total_results": len(merged_results),
        "completed": completed,
        "models": MODELS,
        "score_stats": score_stats,
        "strength_distribution": dict(strengths),
        "agreement_distribution": dict(agreements),
        "round2_mode_distribution": dict(r2_modes),
        "review_required": review_required,
        "disputed_axes": dict(disputed_axes),
        "severe_disputed_axes": dict(severe_axes),
        "method_note": (
            "位置归属度分用于分层和画像，不用于精确排序；R2 默认按 R1 分歧条件触发。"
        ),
    }


def generate_report(
    papers: list[dict[str, Any]],
    metadata: dict[int, dict[str, str]],
    merged_results: list[dict[str, Any]],
    summary: dict[str, Any],
) -> str:
    lines = [
        "# Top101 中国法学自主知识体系位置归属度评估报告",
        "",
        f"生成时间：{summary['generated_at']}",
        f"模型：{', '.join(MODELS)}",
        f"完成：{summary['completed']}/{summary['total_results']}",
        "",
        "## 统计概览",
        "",
        f"- 分数统计：{summary.get('score_stats', {})}",
        f"- 强度分布：{summary.get('strength_distribution', {})}",
        f"- 一致性分布：{summary.get('agreement_distribution', {})}",
        f"- R2 模式分布：{summary.get('round2_mode_distribution', {})}",
        f"- 需复核：{summary.get('review_required', 0)} 篇",
        f"- 分歧轴：{summary.get('disputed_axes', {})}",
        f"- 严重分歧轴：{summary.get('severe_disputed_axes', {})}",
        "",
        "## 逐篇结果",
        "",
        "| # | PID | 期刊 | 年份 | 分数 | 区间 | 强度 | 一致性 | R2 | 复核 | 路径 | 分歧轴 | 题目 |",
        "|---|---:|---|---:|---:|---|---|---|---|---|---|---|---|",
    ]
    result_by_pid = {item["paper_id"]: item for item in merged_results}
    for index, paper in enumerate(papers, start=1):
        pid = int(paper["pid"])
        result = result_by_pid.get(pid, {})
        final = result.get("final") or {}
        meta = metadata.get(pid, {})
        title = meta.get("题目", "")[:36]
        route = (final.get("research_route") or {}).get("primary", "")
        score_range = final.get("score_range", ["", ""])
        lines.append(
            "| {idx} | {pid} | {journal} | {year} | {score} | {rng} | "
            "{strength} | {agreement} | {r2_mode} | {review} | {route} | "
            "{axes} | {title} |".format(
                idx=index,
                pid=pid,
                journal=meta.get("期刊", ""),
                year=meta.get("年份", ""),
                score=final.get("total_score", ""),
                rng=f"{score_range[0]}-{score_range[1]}" if score_range else "",
                strength=final.get("strength", ""),
                agreement=final.get("agreement_level", ""),
                r2_mode=result.get("round2_mode", "not_run"),
                review="是" if final.get("review_required") else "否",
                route=route,
                axes=",".join(final.get("disputed_axes", [])),
                title=title,
            )
        )
    return "\n".join(lines) + "\n"


def _provider_map(model_names: list[str]) -> dict[str, Any]:
    from src.evaluation.providers.factory import create_providers

    providers = create_providers(model_names)
    return {provider.model_name: provider for provider in providers}


async def run_evaluation(args: argparse.Namespace) -> None:
    output_dir = args.output_dir
    setup_logging(output_dir)
    logger.info("Top101 位置归属度评估启动")
    logger.info("模型：%s", ", ".join(MODELS))
    logger.info("论文并发：%s", args.concurrency)
    logger.info("R2 策略：%s", args.r2_policy)

    papers = load_top101(args.ranking)
    if args.dry_run:
        pid = args.pid or int(papers[0]["pid"])
        papers = [paper for paper in papers if int(paper["pid"]) == pid]
        if not papers:
            raise SystemExit(f"PID {pid} 不在 Top101 中")
        logger.info("Dry-run：只评估 PID=%s", pid)
    elif args.limit:
        papers = papers[: args.limit]

    metadata = load_metadata(args.metadata)
    ontology = load_or_build_ontology(
        args.knowledge,
        args.ontology,
        rebuild=args.rebuild_ontology,
    )
    logger.info("Ontology 节点数：%s", len(ontology.nodes))
    provider_map = _provider_map(MODELS)

    r1_dir = output_dir / "round1"
    r2_dir = output_dir / "round2"
    merged_dir = output_dir / "merged"
    for directory in (r1_dir, r2_dir, merged_dir):
        directory.mkdir(parents=True, exist_ok=True)

    paper_tasks: list[tuple[int, Path, dict[str, Any]]] = []
    for paper in papers:
        pid = int(paper["pid"])
        pdf_path = find_pdf(pid, args.paper_dir)
        if pdf_path is None:
            logger.warning("PID=%s PDF 未找到，跳过", pid)
            continue
        paper_meta = {**metadata.get(pid, {}), **paper}
        paper_tasks.append((pid, pdf_path, paper_meta))

    semaphore = asyncio.Semaphore(args.concurrency)

    if args.round in (None, 1):
        r1_results = await asyncio.gather(
            *[
                run_round1_paper(
                    pid=pid,
                    pdf_path=pdf_path,
                    paper_meta=paper_meta,
                    ontology=ontology,
                    provider_map=provider_map,
                    output_dir=r1_dir,
                    semaphore=semaphore,
                    max_text_chars=args.max_text_chars,
                    node_top_k=args.node_top_k,
                )
                for pid, pdf_path, paper_meta in paper_tasks
            ]
        )
        logger.info(
            "[R1] 完成 %s/%s",
            sum(r is not None for r in r1_results),
            len(paper_tasks),
        )

    if args.round in (None, 2):
        r2_jobs = []
        for pid, pdf_path, paper_meta in paper_tasks:
            r1_path = r1_dir / f"paper-{pid}.json"
            if not r1_path.exists():
                logger.warning("[R2] PID=%s 缺少 R1，跳过", pid)
                r2_jobs.append(asyncio.sleep(0, result=None))
                continue
            r1_result = json.loads(r1_path.read_text(encoding="utf-8"))
            if args.r2_policy == "all":
                policy = {
                    "mode": "full",
                    "reason": "forced_full_round2",
                    "reasons": ["forced_full_round2"],
                    "axis_disagreements": [],
                }
            elif args.r2_policy == "skip":
                policy = {
                    "mode": "skip",
                    "reason": "forced_skip_round2",
                    "reasons": ["forced_skip_round2"],
                    "axis_disagreements": [],
                }
            else:
                policy = decide_round2_policy(r1_result)

            mode = policy.get("mode")
            if mode == "skip":
                r2_jobs.append(
                    write_round2_skip_marker(
                        pid=pid,
                        pdf_path=pdf_path,
                        r1_result=r1_result,
                        output_dir=r2_dir,
                        policy=policy,
                    )
                )
                continue

            r2_jobs.append(
                run_round2_paper(
                    pid=pid,
                    pdf_path=pdf_path,
                    paper_meta=paper_meta,
                    ontology=ontology,
                    r1_result=r1_result,
                    provider_map=provider_map,
                    output_dir=r2_dir,
                    semaphore=semaphore,
                    max_text_chars=args.max_text_chars,
                    policy=policy,
                    node_top_k=args.node_top_k,
                )
            )
        r2_results = await asyncio.gather(*r2_jobs)
        logger.info(
            "[R2] 完成 %s/%s",
            sum(r is not None for r in r2_results),
            len(paper_tasks),
        )

    merged_results = []
    for pid, pdf_path, _paper_meta in paper_tasks:
        r1_path = r1_dir / f"paper-{pid}.json"
        r2_path = r2_dir / f"paper-{pid}.json"
        r1_result = (
            json.loads(r1_path.read_text(encoding="utf-8"))
            if r1_path.exists()
            else None
        )
        r2_result = (
            json.loads(r2_path.read_text(encoding="utf-8"))
            if r2_path.exists()
            else None
        )
        merged = merge_paper_result(pid, pdf_path, r1_result, r2_result)
        merged_results.append(merged)
        (merged_dir / f"paper-{pid}.json").write_text(
            json.dumps(merged, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    summary = generate_summary(merged_results)
    (output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    report = generate_report(papers, metadata, merged_results, summary)
    (output_dir / "report.md").write_text(report, encoding="utf-8")

    logger.info("输出目录：%s", output_dir)
    logger.info("汇总：%s", output_dir / "summary.json")
    logger.info("报告：%s", output_dir / "report.md")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Top101 中国法学自主知识体系位置归属度两轮评估"
    )
    parser.add_argument("--round", type=int, choices=[1, 2], default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--pid", type=int)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--concurrency", type=int, default=CONCURRENT_PAPERS)
    parser.add_argument(
        "--r2-policy",
        choices=sorted(ROUND2_POLICIES),
        default="auto",
        help="Round 2 执行策略：auto=按 R1 分歧触发，all=全部完整 R2，skip=全部跳过",
    )
    parser.add_argument("--ranking", type=Path, default=RANKING_PATH)
    parser.add_argument("--metadata", type=Path, default=METADATA_PATH)
    parser.add_argument("--paper-dir", type=Path, default=Path("raw/fullpaper"))
    parser.add_argument("--knowledge", type=Path, default=KNOWLEDGE_PATH)
    parser.add_argument("--ontology", type=Path, default=ONTOLOGY_PATH)
    parser.add_argument("--rebuild-ontology", action="store_true")
    parser.add_argument("--node-top-k", type=int, default=30)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--max-text-chars", type=int, default=MAX_TEXT_CHARS)
    parser.add_argument("--max-knowledge-chars", type=int, default=MAX_KNOWLEDGE_CHARS)
    return parser.parse_args()


def main() -> None:
    asyncio.run(run_evaluation(parse_args()))


if __name__ == "__main__":
    main()
