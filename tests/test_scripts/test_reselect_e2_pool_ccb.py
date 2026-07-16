import asyncio

import pytest

from scripts.e2_new_supplement import ConcurrencyLimitedProvider
from scripts.reselect_e2_pool_ccb import select_pool


PROTOCOL = {
    "mode": "core_ceiling_bonus",
    "total_max": 100,
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
        "bands": [{"min_score": 0, "bonus": 0}],
    },
}


def _dims(score: float) -> dict[str, float]:
    return {
        "problem_originality": score,
        "literature_insight": score,
        "analytical_framework": score,
        "logical_coherence": score,
        "conclusion_consensus": score,
        "forward_extension": score,
    }


def test_subject_and_year_supplements_never_bypass_hard_e1_threshold():
    e1 = {1: _dims(90), 2: _dims(79), 3: _dims(85)}
    axis5 = {1: 9, 2: 10, 3: 9}
    meta = {
        "subject": {1: "A", 2: "B", 3: "A"},
        "year": {1: "2020", 2: "2021", 3: "2020"},
        "info": {},
    }

    pool, stats = select_pool(e1, axis5, meta, PROTOCOL)

    assert set(pool) == {1, 3}
    assert 2 not in pool
    assert stats["eligible"] == 2
    assert stats["subject_shortfalls"]["B"] == 5
    assert stats["year_shortfalls"]["2021"] == 5


@pytest.mark.asyncio
async def test_e2_supplement_uses_one_global_api_concurrency_gate():
    active = 0
    peak = 0
    lock = asyncio.Lock()

    class Provider:
        model_name = "fake"

        async def generate_json_response(self, prompt: str) -> dict:
            nonlocal active, peak
            async with lock:
                active += 1
                peak = max(peak, active)
            await asyncio.sleep(0.01)
            async with lock:
                active -= 1
            return {"ok": True}

    semaphore = asyncio.Semaphore(2)
    provider = ConcurrencyLimitedProvider(Provider(), semaphore)

    await asyncio.gather(
        *(provider.generate_json_response("prompt") for _ in range(8))
    )

    assert peak == 2
