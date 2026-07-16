import asyncio
from dataclasses import dataclass

import pytest

from src.evaluation.cross_review import CrossReviewService
from src.evaluation.schemas import DimensionResult
from src.ingestion.schemas import ProcessedPaper
from src.knowledge.loader import load_framework


@dataclass
class FakeCrossProvider:
    model_name: str
    revised_score: int

    async def generate_json_response(self, prompt: str) -> dict:
        await asyncio.sleep(0)
        return {
            "original_score": self.revised_score - 1,
            "revised_score": self.revised_score,
            "score_changed": True,
            "change_direction": "up",
            "change_magnitude": 1,
            "revised_band": "good",
            "revised_core_judgment": "复核判断",
            "revision_rationale": "复核理由",
            "accepted_points": [],
            "rejected_points": ["保留实质分歧"],
            "new_evidence_found": ["证据"],
            "confidence": "medium",
        }


def _r1(model: str, score: int) -> DimensionResult:
    return DimensionResult(
        dimension="problem_originality",
        score=score,
        evidence_quotes=["原证据"],
        analysis="第一轮",
        model_name=model,
    )


def test_cross_review_requires_at_least_one_provider_in_each_group():
    service = CrossReviewService()

    with pytest.raises(ValueError, match="宽松组和严格组"):
        service.validate_provider_names(["glm-5.1", "qwen3.6-plus"])


@pytest.mark.asyncio
async def test_cross_review_uses_opposite_group_and_returns_structured_payload():
    service = CrossReviewService()
    framework = load_framework("configs/frameworks/law-v2.56.6-20260522.yaml")
    dimension = framework.dimensions[0]
    providers = [
        FakeCrossProvider("glm-5.1", 78),
        FakeCrossProvider("deepseek-v4-pro", 72),
    ]
    r1 = {
        "glm-5.1": _r1("glm-5.1", 80),
        "deepseek-v4-pro": _r1("deepseek-v4-pro", 70),
    }

    outcomes = await service.evaluate_dimension(
        providers,
        dimension,
        ProcessedPaper(body="正文", full_text="正文", structure_status="detected"),
        r1,
    )

    assert {outcome.result.model_name for outcome in outcomes} == {
        "glm-5.1",
        "deepseek-v4-pro",
    }
    assert {outcome.result.score for outcome in outcomes} == {72, 78}
    assert all(outcome.raw_payload["rejected_points"] for outcome in outcomes)


def test_unresolved_std_routes_to_expert_review_only():
    service = CrossReviewService()

    assert service.requires_expert_review(8.01) is True
    assert service.requires_expert_review(8.0) is False
    assert service.protocol["unresolved_disagreement"]["action"] == "expert_review"


@pytest.mark.asyncio
async def test_cross_review_retries_transient_provider_failure():
    class FlakyProvider(FakeCrossProvider):
        calls = 0

        async def generate_json_response(self, prompt: str) -> dict:
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("temporary")
            return await super().generate_json_response(prompt)

    service = CrossReviewService()
    dimension = load_framework(
        "configs/frameworks/law-v2.56.6-20260522.yaml"
    ).dimensions[0]
    flaky = FlakyProvider("glm-5.1", 78)
    strict = FakeCrossProvider("deepseek-v4-pro", 72)

    outcomes = await service.evaluate_dimension(
        [flaky, strict],
        dimension,
        ProcessedPaper(body="正文", full_text="正文", structure_status="detected"),
        {
            "glm-5.1": _r1("glm-5.1", 80),
            "deepseek-v4-pro": _r1("deepseek-v4-pro", 70),
        },
    )

    assert len(outcomes) == 2
    assert flaky.calls == 2
