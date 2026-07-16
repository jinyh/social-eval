from src.evaluation.integrity import raw_payload_coverage, validate_e2_pool_records


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


def test_e2_raw_coverage_supports_legacy_and_explicit_round2_payloads():
    models = ["deepseek-v4-pro", "glm-5.1", "kimi-k2.6", "qwen3.6-plus"]
    legacy = {
        "dimensions": {
            "d1": {
                "raw_outputs": {model: {} for model in models[:3]},
                "round2_raw_outputs": {models[3]: {}},
            }
        }
    }
    current = {
        "dimensions": {
            "d1": {
                "raw_outputs": {model: {"score": 1} for model in models},
                "round2_raw_outputs": {
                    model: {"revised_score": 1} for model in models
                },
            }
        }
    }

    coverage = raw_payload_coverage(
        [legacy, current], ("d1",), mode="e2_r2"
    )

    assert coverage == {"expected": 8, "present": 8, "missing": 0}
