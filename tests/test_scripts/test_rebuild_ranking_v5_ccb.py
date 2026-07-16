from scripts.rebuild_ranking_v5_ccb import DIM_ZH, WEIGHTS
from src.knowledge.registry import load_scoring_protocol


def test_ranking_dimension_keys_match_pooling_and_scoring_protocol() -> None:
    protocol = load_scoring_protocol()
    protocol_keys = {
        *(item["key"] for item in protocol["core_dimensions"]),
        protocol["ceiling_dimension"]["key"],
        protocol["bonus_dimension"]["key"],
    }

    assert set(WEIGHTS) == set(DIM_ZH)
    assert protocol_keys <= set(WEIGHTS)
