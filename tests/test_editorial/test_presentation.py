from src.editorial.formal_check import evaluate_formal_completeness
from src.editorial.policy import load_editorial_policy
from src.editorial.presentation import (
    build_ccb_summary,
    build_position_summary,
    build_six_dimension_summary,
)
from src.models.evaluation import DimensionScore
from src.models.reliability import ReliabilityResult


def _score(
    dimension_key: str,
    model_name: str,
    score: float,
    band: str,
) -> DimensionScore:
    return DimensionScore(
        task_id="task-1",
        dimension_key=dimension_key,
        model_name=model_name,
        score=score,
        evidence_quotes=["示例证据"],
        analysis="示例分析",
        structured_payload={"band": band},
        round_number=2,
    )


def test_four_model_summary_counts_real_disagreement_and_anonymizes_models() -> None:
    policy = load_editorial_policy("jiaoda-law-v1")
    models = ["模型一", "模型二", "模型三", "模型四"]
    scores = [
        _score("problem_originality", model, score, band)
        for model, score, band in zip(
            models,
            [52, 58, 74, 86],
            ["marginal", "marginal", "good", "excellent"],
            strict=True,
        )
    ]
    reliability = [
        ReliabilityResult(
            task_id="task-1",
            dimension_key="problem_originality",
            mean_score=67.5,
            std_score=15.2,
            is_high_confidence=False,
            round_number=2,
        )
    ]

    result = build_six_dimension_summary(scores, reliability, policy, models)

    assert result["model_participation"] == {
        "count": 4,
        "labels": ["模型甲", "模型乙", "模型丙", "模型丁"],
    }
    assert result["difference_count"] == 1
    assert result["expert_review_dimension_count"] == 1
    dimension = result["dimensions"][0]
    assert dimension["dimension_name"] == "研究创新性"
    assert dimension["requires_expert_review"] is True
    assert [item["model_label"] for item in dimension["model_results"]] == [
        "模型甲",
        "模型乙",
        "模型丙",
        "模型丁",
    ]
    assert not any(model in str(result) for model in models)


def test_band_difference_below_expert_threshold_is_still_visible() -> None:
    policy = load_editorial_policy("jiaoda-law-v1")
    models = ["甲供应方", "乙供应方", "丙供应方", "丁供应方"]
    scores = [
        _score("logical_coherence", model, score, band)
        for model, score, band in zip(
            models,
            [58, 60, 61, 62],
            ["marginal", "good", "good", "good"],
            strict=True,
        )
    ]
    reliability = [
        ReliabilityResult(
            task_id="task-1",
            dimension_key="logical_coherence",
            mean_score=60.25,
            std_score=1.71,
            is_high_confidence=True,
            round_number=2,
        )
    ]

    result = build_six_dimension_summary(scores, reliability, policy, models)

    assert result["difference_count"] == 1
    assert result["expert_review_dimension_count"] == 0
    assert result["dimensions"][0]["difference_label"] == "存在观点差异"


def test_ccb_and_five_axis_are_described_as_separate_reference_outputs() -> None:
    ccb = build_ccb_summary(
        {
            "base_score": 86.4,
            "bonus_score": 1.61,
            "conclusion_consensus_ceiling": 90,
            "final_score": 88.01,
        }
    )
    position = build_position_summary(
        {
            "final": {
                "total_score": 9,
                "strength": "strong",
                "confidence": "medium",
                "agreement_level": "medium",
                "review_required": False,
                "axis_scores": {
                    "object_belonging": {
                        "score": 2,
                        "score_range": [1, 2],
                        "evidence_quotes": ["研究对象证据"],
                    }
                },
            }
        },
        precheck_result={"conclusion": "boundary_review"},
    )

    assert ccb is not None
    assert ccb["final_score"] == 88.01
    assert "不作为录用或退稿阈值" in ccb["notice"]
    assert position is not None
    assert position["total_score"] == 9
    assert position["conflict_with_precheck"] is True
    assert position["axes"][0]["axis_name"] == "对象归属度"
    assert position["axes"][0]["has_model_difference"] is True
    assert "不评价论文质量" in position["notice"]


def test_formal_completeness_requires_editor_confirmation_at_boundary() -> None:
    incomplete = evaluate_formal_completeness("一段很短的正文")
    complete = evaluate_formal_completeness(
        "摘要\n"
        + "这是可解析的法学论文正文。" * 250
        + "\n一、问题提出\n注释：① 示例引注\n参考文献"
    )

    assert incomplete["status"] == "boundary"
    assert incomplete["requires_editor_confirmation"] is True
    assert complete["status"] == "pass"
    assert complete["requires_editor_confirmation"] is False
