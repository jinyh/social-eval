from src.evaluation.providers.utils import normalize_json_keys


def test_normalize_json_keys_strips_leading_commas():
    data = {"a": 1, ",b": [{", c": 2}], ",\td": "x"}
    assert normalize_json_keys(data) == {"a": 1, "b": [{"c": 2}], "d": "x"}


def test_normalize_json_keys_keeps_valid_keys_and_values():
    data = {
        "score": 85,
        "evidence_quotes": ["原文，含逗号"],
        "limit_rule_triggered": [],
    }
    assert normalize_json_keys(data) == data
