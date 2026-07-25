from src.editorial.label_evaluation import (
    align_issue_lists,
    evaluate_decision_alignment,
)


def test_issue_alignment_matches_related_issues_one_to_one() -> None:
    result = align_issue_lists(
        ["核心概念定义不稳定", "未回应主要反对观点"],
        ["核心概念前后使用不一致", "缺少对反对意见的回应"],
    )

    assert result.mean_best_match > 0
    assert len(result.matched_pairs) == 2
    assert result.issue_count_difference == 0


def test_decision_metrics_exclude_unspecified_accept_from_four_class() -> None:
    result = evaluate_decision_alignment(
        [
            {"human_decision": "reject", "ai_decision": "reject"},
            {
                "human_decision": "accept_unspecified",
                "ai_decision": "minor_accept",
            },
            {
                "human_decision": "major_revision",
                "ai_decision": "minor_accept",
            },
        ]
    )

    assert result["three_class"] == {"sample_count": 3, "accuracy": 2 / 3}
    assert result["four_class"] == {"sample_count": 2, "accuracy": 0.5}
