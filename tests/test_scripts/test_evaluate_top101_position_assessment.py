from scripts.evaluate_top101_position_assessment_two_rounds import (
    AXIS_KEYS,
    CONCURRENT_PAPERS,
    aggregate_final_assessment,
    build_round1_prompt,
    decide_round2_policy,
    enforce_light_round2_axis_agreement,
    format_retrieved_nodes_for_prompt,
    merge_paper_result,
    normalize_assessment,
    strength_for_score,
)
from src.knowledge.node_retrieval import RetrievedNode


def _assessment(scores: dict[str, int]) -> dict:
    return {
        "research_route": {"primary": "chinese_doctrinal", "secondary": []},
        "axis_scores": {
            axis: {"score": score, "evidence_quotes": [f"{axis} evidence"]}
            for axis, score in scores.items()
        },
        "total_score": sum(scores.values()),
        "strength": "medium",
        "confidence": "high",
        "risks": [],
    }


def _r1_result(*assessments: dict) -> dict:
    return {
        "paper_id": 1,
        "models": {
            "deepseek-v4-pro": assessments[0],
            "qwen3.6-plus": assessments[1],
        },
    }


def test_default_paper_concurrency_is_five():
    assert CONCURRENT_PAPERS == 5


def test_strength_for_position_assessment_score():
    assert strength_for_score(10) == "strong"
    assert strength_for_score(8) == "strong"
    assert strength_for_score(7) == "medium"
    assert strength_for_score(5) == "medium"
    assert strength_for_score(4) == "weak"
    assert strength_for_score(2) == "weak"
    assert strength_for_score(1) == "absent"


def test_normalize_assessment_recalculates_axis_total_and_strength():
    raw = _assessment(
        {
            "object_belonging": 2,
            "material_belonging": 2,
            "category_autonomy": 1,
            "explanatory_orientation": 2,
            "system_mappability": 0,
        }
    )
    raw["total_score"] = 10

    normalized = normalize_assessment(raw)

    assert normalized["total_score"] == 7
    assert normalized["strength"] == "medium"
    assert set(normalized["axis_scores"]) == set(AXIS_KEYS)


def test_aggregate_final_assessment_does_not_average_severe_axis_disagreement():
    qwen = _assessment({axis: 2 for axis in AXIS_KEYS})
    deepseek = _assessment(
        {
            "object_belonging": 2,
            "material_belonging": 2,
            "category_autonomy": 0,
            "explanatory_orientation": 2,
            "system_mappability": 0,
        }
    )

    final = aggregate_final_assessment(
        {"qwen3.6-plus": qwen, "deepseek-v4-pro": deepseek}
    )

    assert final["axis_scores"]["category_autonomy"]["score"] == 0
    assert final["axis_scores"]["system_mappability"]["score"] == 0
    assert final["score_range"] == [6, 10]
    assert final["agreement_level"] == "low"
    assert final["review_required"] is True
    assert "category_autonomy" in final["disputed_axes"]
    assert "system_mappability" in final["disputed_axes"]


def test_aggregate_final_assessment_keeps_neighbor_disagreement_as_range():
    qwen = _assessment({axis: 2 for axis in AXIS_KEYS})
    deepseek = _assessment(
        {
            "object_belonging": 2,
            "material_belonging": 2,
            "category_autonomy": 1,
            "explanatory_orientation": 2,
            "system_mappability": 1,
        }
    )

    final = aggregate_final_assessment(
        {"qwen3.6-plus": qwen, "deepseek-v4-pro": deepseek}
    )

    assert final["total_score"] == 8
    assert final["score_range"] == [8, 10]
    assert final["agreement_level"] == "medium"
    assert final["review_required"] is False
    assert final["axis_scores"]["category_autonomy"]["score"] == 1
    assert final["axis_scores"]["category_autonomy"]["model_scores"] == {
        "qwen3.6-plus": 2,
        "deepseek-v4-pro": 1,
    }


def test_round2_policy_skips_when_r1_models_fully_agree():
    deepseek = _assessment({axis: 2 for axis in AXIS_KEYS})
    qwen = _assessment({axis: 2 for axis in AXIS_KEYS})

    policy = decide_round2_policy(_r1_result(deepseek, qwen))

    assert policy["mode"] == "skip"
    assert policy["reason"] == "r1_full_agreement"


def test_round2_policy_uses_light_review_for_route_disagreement_only():
    deepseek = _assessment({axis: 2 for axis in AXIS_KEYS})
    qwen = _assessment({axis: 2 for axis in AXIS_KEYS})
    qwen["research_route"]["primary"] = "comparative_localization"

    policy = decide_round2_policy(_r1_result(deepseek, qwen))

    assert policy["mode"] == "light"
    assert "route_primary_disagreement" in policy["reasons"]


def test_round2_policy_skips_when_system_nodes_are_compatible():
    deepseek = _assessment({axis: 2 for axis in AXIS_KEYS})
    qwen = _assessment({axis: 2 for axis in AXIS_KEYS})
    deepseek["axis_scores"]["system_mappability"]["existing_nodes"] = [
        "商法学：公司治理、商事主体",
        "民法学：债务承担",
    ]
    qwen["axis_scores"]["system_mappability"]["existing_nodes"] = [
        "商法学-公司治理/资本制度",
        "民法学-债法总则/债务承担",
    ]

    policy = decide_round2_policy(_r1_result(deepseek, qwen))

    assert policy["mode"] == "skip"


def test_round2_policy_uses_light_review_for_system_root_conflict():
    deepseek = _assessment({axis: 2 for axis in AXIS_KEYS})
    qwen = _assessment({axis: 2 for axis in AXIS_KEYS})
    deepseek["axis_scores"]["system_mappability"]["existing_nodes"] = [
        "商法学：公司治理"
    ]
    qwen["axis_scores"]["system_mappability"]["existing_nodes"] = ["刑法学：犯罪论"]

    policy = decide_round2_policy(_r1_result(deepseek, qwen))

    assert policy["mode"] == "light"
    assert "system_node_conflict" in policy["reasons"]


def test_round2_policy_skips_when_structured_node_ids_match():
    deepseek = _assessment({axis: 2 for axis in AXIS_KEYS})
    qwen = _assessment({axis: 2 for axis in AXIS_KEYS})
    deepseek["axis_scores"]["system_mappability"]["validated_node_matches"] = [
        {"node_id": "d05.concept.001", "status": "accepted"}
    ]
    qwen["axis_scores"]["system_mappability"]["validated_node_matches"] = [
        {"node_id": "d05.concept.001", "status": "accepted"}
    ]

    policy = decide_round2_policy(_r1_result(deepseek, qwen))

    assert policy["mode"] == "skip"


def test_round2_policy_uses_light_review_for_structured_node_root_conflict():
    deepseek = _assessment({axis: 2 for axis in AXIS_KEYS})
    qwen = _assessment({axis: 2 for axis in AXIS_KEYS})
    deepseek["axis_scores"]["system_mappability"]["validated_node_matches"] = [
        {"node_id": "d06.concept.001", "status": "accepted"}
    ]
    qwen["axis_scores"]["system_mappability"]["validated_node_matches"] = [
        {"node_id": "d11.concept.001", "status": "accepted"}
    ]

    policy = decide_round2_policy(_r1_result(deepseek, qwen))

    assert policy["mode"] == "light"
    assert "system_node_conflict" in policy["reasons"]


def test_round2_policy_uses_full_review_for_axis_disagreement():
    deepseek = _assessment({axis: 2 for axis in AXIS_KEYS})
    qwen = _assessment({axis: 2 for axis in AXIS_KEYS})
    qwen["axis_scores"]["category_autonomy"]["score"] = 1

    policy = decide_round2_policy(_r1_result(deepseek, qwen))

    assert policy["mode"] == "full"
    assert "axis_score_disagreement:category_autonomy" in policy["reasons"]


def test_round2_policy_uses_full_review_for_low_confidence():
    deepseek = _assessment({axis: 2 for axis in AXIS_KEYS})
    qwen = _assessment({axis: 2 for axis in AXIS_KEYS})
    qwen["confidence"] = "low"

    policy = decide_round2_policy(_r1_result(deepseek, qwen))

    assert policy["mode"] == "full"
    assert "low_confidence:qwen3.6-plus" in policy["reasons"]


def test_round1_prompt_uses_retrieved_nodes_not_full_knowledge_excerpt():
    node_text = format_retrieved_nodes_for_prompt(
        [
            RetrievedNode(
                node_id="d05.concept.001",
                label="占有保护",
                path="民法学 > 标识性概念 > 占有保护",
                node_type="concept",
                score=0.9,
                match_methods=["keyword"],
            )
        ]
    )

    prompt = build_round1_prompt(
        paper_meta={"题目": "数字私力救济", "期刊": "法学研究", "年份": "2023"},
        paper_text="本文讨论占有保护。",
        knowledge_excerpt="SHOULD_NOT_APPEAR_FULL_KNOWLEDGE",
        node_candidates_text=node_text,
    )

    assert "候选知识体系节点" in prompt
    assert "d05.concept.001" in prompt
    assert "占有保护" in prompt
    assert "SHOULD_NOT_APPEAR_FULL_KNOWLEDGE" not in prompt


def test_light_round2_preserves_axis_scores_when_round1_axes_agreed():
    deepseek_r1 = _assessment({axis: 2 for axis in AXIS_KEYS})
    qwen_r1 = _assessment({axis: 2 for axis in AXIS_KEYS})
    qwen_r1["research_route"]["primary"] = "comparative_localization"
    r1_result = _r1_result(deepseek_r1, qwen_r1)

    light_output = _assessment({axis: 0 for axis in AXIS_KEYS})
    light_output["confidence"] = "low"

    corrected = enforce_light_round2_axis_agreement(
        light_output,
        r1_result=r1_result,
        model_name="deepseek-v4-pro",
    )

    assert corrected["total_score"] == 10
    assert corrected["strength"] == "strong"
    assert corrected["light_round2_score_overrides"] == {
        "object_belonging": {"from": 0, "to": 2},
        "material_belonging": {"from": 0, "to": 2},
        "category_autonomy": {"from": 0, "to": 2},
        "explanatory_orientation": {"from": 0, "to": 2},
        "system_mappability": {"from": 0, "to": 2},
    }


def test_merge_reconciles_existing_light_round2_outputs_when_r1_axes_agreed(tmp_path):
    deepseek_r1 = _assessment({axis: 2 for axis in AXIS_KEYS})
    qwen_r1 = _assessment({axis: 2 for axis in AXIS_KEYS})
    qwen_r1["research_route"]["primary"] = "comparative_localization"
    r1_result = _r1_result(deepseek_r1, qwen_r1)
    r2_result = {
        "round2_mode": "light",
        "models": {
            "deepseek-v4-pro": _assessment({axis: 0 for axis in AXIS_KEYS}),
            "qwen3.6-plus": _assessment({axis: 2 for axis in AXIS_KEYS}),
        },
    }

    merged = merge_paper_result(
        pid=1,
        pdf_path=tmp_path / "0001-x.pdf",
        r1_result=r1_result,
        r2_result=r2_result,
    )

    assert merged["final"]["total_score"] == 10
    assert merged["final"]["score_range"] == [10, 10]
    assert merged["final"]["review_required"] is False
