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


def test_peer_review_requires_the_complete_candidate_model_set():
    service = CrossReviewService.for_model_set("six-dimension-v2-candidate")

    with pytest.raises(ValueError, match="完整候选模型集"):
        service.validate_provider_names(
            [
                "glm-5.2",
                "qwen3.7-max-2026-06-08",
                "deepseek-v4-pro",
            ]
        )


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
    glm_outcome = next(
        outcome for outcome in outcomes if outcome.result.model_name == "glm-5.1"
    )
    assert "deepseek-v4-pro" in glm_outcome.prompt
    assert "qwen3.6-plus" not in glm_outcome.prompt


@pytest.mark.asyncio
async def test_peer_review_shares_three_anonymous_r1_reviews_and_audits_mapping():
    class CapturingProvider(FakeCrossProvider):
        prompt: str = ""

        async def generate_json_response(self, prompt: str) -> dict:
            self.prompt = prompt
            return await super().generate_json_response(prompt)

    service = CrossReviewService.for_model_set("six-dimension-v2-candidate")
    dimension = load_framework(
        "configs/frameworks/law-v2.56.6-20260522.yaml"
    ).dimensions[0]
    names = [
        "glm-5.2",
        "qwen3.7-max-2026-06-08",
        "deepseek-v4-pro",
        "kimi-k2.6",
    ]
    providers = [
        CapturingProvider(name, revised_score=80 + index)
        for index, name in enumerate(names)
    ]
    r1 = {name: _r1(name, 70 + index) for index, name in enumerate(names)}

    outcomes = await service.evaluate_dimension(
        providers,
        dimension,
        ProcessedPaper(body="正文", full_text="正文", structure_status="detected"),
        r1,
    )

    assert len(outcomes) == 4
    for provider, outcome in zip(providers, outcomes, strict=True):
        assert all(name not in provider.prompt for name in names)
        assert provider.prompt.count('"review_label": "评审意见') == 3
        mapping = outcome.raw_payload["_cross_review_metadata"][
            "anonymous_peer_mapping"
        ]
        assert list(mapping) == ["评审意见1", "评审意见2", "评审意见3"]
        assert set(mapping.values()) == set(names) - {provider.model_name}


@pytest.mark.asyncio
async def test_peer_review_waits_when_any_r1_result_is_missing():
    service = CrossReviewService.for_model_set("six-dimension-v2-candidate")
    dimension = load_framework(
        "configs/frameworks/law-v2.56.6-20260522.yaml"
    ).dimensions[0]
    names = [
        "glm-5.2",
        "qwen3.7-max-2026-06-08",
        "deepseek-v4-pro",
        "kimi-k2.6",
    ]
    providers = [FakeCrossProvider(name, 80) for name in names]
    r1 = {name: _r1(name, 75) for name in names[:-1]}

    with pytest.raises(ValueError, match="等待四模型第一轮评价齐全"):
        await service.evaluate_dimension(
            providers,
            dimension,
            ProcessedPaper(
                body="正文",
                full_text="正文",
                structure_status="detected",
            ),
            r1,
        )


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


@pytest.mark.asyncio
async def test_cross_review_normalizes_non_list_evidence_to_empty_list():
    class BooleanEvidenceProvider(FakeCrossProvider):
        async def generate_json_response(self, prompt: str) -> dict:
            payload = await super().generate_json_response(prompt)
            payload["new_evidence_found"] = False
            return payload

    service = CrossReviewService()
    dimension = load_framework(
        "configs/frameworks/law-v2.56.6-20260522.yaml"
    ).dimensions[0]
    lenient = BooleanEvidenceProvider("glm-5.1", 78)
    strict = FakeCrossProvider("deepseek-v4-pro", 72)

    outcomes = await service.evaluate_dimension(
        [lenient, strict],
        dimension,
        ProcessedPaper(body="正文", full_text="正文", structure_status="detected"),
        {
            "glm-5.1": _r1("glm-5.1", 80),
            "deepseek-v4-pro": _r1("deepseek-v4-pro", 70),
        },
    )

    outcome = next(item for item in outcomes if item.result.model_name == "glm-5.1")
    assert outcome.result.evidence_quotes == []


@pytest.mark.asyncio
async def test_cross_review_normalizes_structured_evidence_quote_objects():
    class StructuredEvidenceProvider(FakeCrossProvider):
        async def generate_json_response(self, prompt: str) -> dict:
            payload = await super().generate_json_response(prompt)
            payload["new_evidence_found"] = [
                {"quote": "可核验证据", "location": "正文"},
                {"evidence_quote": "补充证据"},
            ]
            return payload

    service = CrossReviewService()
    dimension = load_framework(
        "configs/frameworks/law-v2.56.6-20260522.yaml"
    ).dimensions[0]
    lenient = StructuredEvidenceProvider("glm-5.1", 78)
    strict = FakeCrossProvider("deepseek-v4-pro", 72)

    outcomes = await service.evaluate_dimension(
        [lenient, strict],
        dimension,
        ProcessedPaper(body="正文", full_text="正文", structure_status="detected"),
        {
            "glm-5.1": _r1("glm-5.1", 80),
            "deepseek-v4-pro": _r1("deepseek-v4-pro", 70),
        },
    )

    outcome = next(item for item in outcomes if item.result.model_name == "glm-5.1")
    assert outcome.result.evidence_quotes == ["可核验证据", "补充证据"]


@pytest.mark.asyncio
async def test_cross_review_compacts_context_after_content_inspection_failure():
    class ContentInspectionProvider(FakeCrossProvider):
        calls = 0

        async def generate_json_response(self, prompt: str) -> dict:
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("data_inspection_failed")
            assert "内容审查重试：中间论证已省略" in prompt
            return await super().generate_json_response(prompt)

    service = CrossReviewService()
    dimension = load_framework(
        "configs/frameworks/law-v2.56.6-20260522.yaml"
    ).dimensions[0]
    lenient = ContentInspectionProvider("glm-5.1", 78)
    strict = FakeCrossProvider("deepseek-v4-pro", 72)

    outcomes = await service.evaluate_dimension(
        [lenient, strict],
        dimension,
        ProcessedPaper(
            body="甲" * 20_000,
            full_text="甲" * 20_000,
            structure_status="detected",
        ),
        {
            "glm-5.1": _r1("glm-5.1", 80),
            "deepseek-v4-pro": _r1("deepseek-v4-pro", 70),
        },
    )

    outcome = next(item for item in outcomes if item.result.model_name == "glm-5.1")
    assert lenient.calls == 2
    assert (
        outcome.raw_payload["_cross_review_metadata"]["content_inspection_fallback"]
        is True
    )


@pytest.mark.asyncio
async def test_cross_review_retries_response_without_revised_score():
    class MissingScoreProvider(FakeCrossProvider):
        calls = 0

        async def generate_json_response(self, prompt: str) -> dict:
            self.calls += 1
            if self.calls == 1:
                return {"revision_rationale": "缺少分数"}
            return await super().generate_json_response(prompt)

    service = CrossReviewService()
    dimension = load_framework(
        "configs/frameworks/law-v2.56.6-20260522.yaml"
    ).dimensions[0]
    lenient = MissingScoreProvider("glm-5.1", 78)
    strict = FakeCrossProvider("deepseek-v4-pro", 72)

    outcomes = await service.evaluate_dimension(
        [lenient, strict],
        dimension,
        ProcessedPaper(body="正文", full_text="正文", structure_status="detected"),
        {
            "glm-5.1": _r1("glm-5.1", 80),
            "deepseek-v4-pro": _r1("deepseek-v4-pro", 70),
        },
    )

    assert lenient.calls == 2
    assert (
        next(
            item for item in outcomes if item.result.model_name == "glm-5.1"
        ).result.score
        == 78
    )
