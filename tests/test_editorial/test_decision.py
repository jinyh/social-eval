from src.editorial.decision import (
    build_recommendation,
    calculate_candidate_decision,
)
from src.editorial.policy import load_editorial_policy


def _bands(default: str = "good") -> dict[str, str]:
    return {
        "problem_originality": default,
        "literature_insight": default,
        "analytical_framework": default,
        "logical_coherence": default,
        "conclusion_consensus": default,
        "forward_extension": default,
    }


def test_defect_first_mapping_declines_without_external_review() -> None:
    policy = load_editorial_policy("jiaoda-law-v1")
    bands = _bands()
    bands["analytical_framework"] = "unacceptable"

    assert calculate_candidate_decision(bands, policy) == "decline_without_review"


def test_priority_review_requires_logic_and_three_excellent_core_dimensions() -> None:
    policy = load_editorial_policy("jiaoda-law-v1")
    bands = _bands()
    for key in (
        "problem_originality",
        "literature_insight",
        "logical_coherence",
    ):
        bands[key] = "excellent"

    assert calculate_candidate_decision(bands, policy) == "priority_external_review"


def test_position_and_ccb_are_not_decision_inputs() -> None:
    policy = load_editorial_policy("oriental-law-v1")
    bands = _bands()

    assert calculate_candidate_decision(bands, policy) == "send_external_review"


def test_shadow_and_expert_review_withhold_recommendation() -> None:
    policy = load_editorial_policy("academic-monthly-law-v1")

    result = build_recommendation(
        _bands(),
        policy,
        rollout_state="shadow",
        requires_expert_review=True,
    )

    assert result.candidate_decision == "send_external_review"
    assert result.state == "withheld"
    assert result.withheld_reasons == (
        "editorial_unit_shadow",
        "expert_review_required",
    )
