from src.reporting.scoring import calculate_weighted_total


def test_core_ceiling_bonus_protocol_uses_core_score_with_ceiling_and_bonus():
    protocol = {
        "mode": "core_ceiling_bonus",
        "core_dimensions": [
            {"key": "problem_originality", "weight": 0.30},
            {"key": "literature_insight", "weight": 0.20},
            {"key": "analytical_framework", "weight": 0.15},
            {"key": "logical_coherence", "weight": 0.20},
        ],
        "ceiling_dimension": {
            "key": "conclusion_consensus",
            "thresholds": [
                {"min_score": 75, "score_ceiling": None},
                {"min_score": 60, "score_ceiling": 75},
                {"min_score": 0, "score_ceiling": 65},
            ],
        },
        "bonus_dimension": {
            "key": "forward_extension",
            "max_bonus": 5,
            "prerequisites": {
                "logical_coherence_min": 60,
                "conclusion_consensus_min": 60,
                "core_dimension_min": 50,
            },
            "bands": [
                {"min_score": 80, "bonus": 5},
                {"min_score": 60, "bonus": 3},
                {"min_score": 40, "bonus": 2},
                {"min_score": 0, "bonus": 0},
            ],
        },
    }
    dimension_scores = {
        "problem_originality": 90,
        "literature_insight": 80,
        "analytical_framework": 70,
        "logical_coherence": 80,
        "conclusion_consensus": 65,
        "forward_extension": 90,
    }

    total = calculate_weighted_total(dimension_scores, protocol)

    # Core score is 81.76, FE adds 5, then CC 65 limits final score to 75.
    assert total == 75.0


def test_forward_extension_bonus_is_disabled_when_core_dimension_collapses():
    protocol = {
        "mode": "core_ceiling_bonus",
        "core_dimensions": [
            {"key": "problem_originality", "weight": 0.30},
            {"key": "literature_insight", "weight": 0.20},
            {"key": "analytical_framework", "weight": 0.15},
            {"key": "logical_coherence", "weight": 0.20},
        ],
        "ceiling_dimension": {
            "key": "conclusion_consensus",
            "thresholds": [{"min_score": 0, "score_ceiling": None}],
        },
        "bonus_dimension": {
            "key": "forward_extension",
            "max_bonus": 5,
            "prerequisites": {
                "logical_coherence_min": 60,
                "conclusion_consensus_min": 60,
                "core_dimension_min": 50,
            },
            "bands": [{"min_score": 80, "bonus": 5}, {"min_score": 0, "bonus": 0}],
        },
    }
    dimension_scores = {
        "problem_originality": 90,
        "literature_insight": 45,
        "analytical_framework": 70,
        "logical_coherence": 80,
        "conclusion_consensus": 90,
        "forward_extension": 95,
    }

    total = calculate_weighted_total(dimension_scores, protocol)

    assert total == 73.53


def test_legacy_weighted_total_is_preserved_without_protocol():
    dimension_scores = {
        "problem_originality": 80,
        "literature_insight": 70,
    }
    dimension_weights = {
        "problem_originality": 0.30,
        "literature_insight": 0.15,
    }

    total = calculate_weighted_total(dimension_scores, None, dimension_weights)

    assert total == 34.5
