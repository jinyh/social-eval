from src.evaluation.integrity import validate_e2_pool_records


def test_e2_integrity_rejects_any_hard_threshold_bypass():
    errors = validate_e2_pool_records(
        [
            {"id": 1, "e1_score": 80, "axis5_total": 9},
            {"id": 2, "e1_score": 79.99, "axis5_total": 10},
            {"id": 3, "e1_score": 90, "axis5_total": 8},
        ]
    )

    assert errors == [
        "paper-2: E1 CCB 79.99 < 80",
        "paper-3: 五轴 8.0 < 9",
    ]
