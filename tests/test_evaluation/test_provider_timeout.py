"""测试 provider 超时机制：确保超时不会挂死 pipeline，而是走降级路径。"""

import asyncio

import pytest

from src.core.exceptions import (
    ProviderResponseValidationError,
    ProviderTimeoutError,
)
from src.evaluation.concurrent_evaluator import _call_with_timing
from src.evaluation.providers.base import BaseProvider
from src.evaluation.schemas import DimensionResult, LimitRuleTriggered
from src.knowledge.schemas import Dimension


class SlowProvider(BaseProvider):
    """模拟超时的 provider"""

    def __init__(self, delay: float = 10.0):
        self.model_name = "slow-model"
        self.timeout = 0.1  # 100ms 超时，用于快速测试
        self._delay = delay

    async def generate_json_response(self, prompt: str) -> dict:
        await asyncio.sleep(self._delay)
        return {}

    async def evaluate_dimension(self, prompt: str) -> DimensionResult:
        await asyncio.sleep(self._delay)
        return DimensionResult(
            dimension="test", score=80, evidence_quotes=[], model_name=self.model_name
        )


class FastProvider(BaseProvider):
    """正常返回的 provider"""

    def __init__(self):
        self.model_name = "fast-model"
        self.timeout = 5.0

    async def generate_json_response(self, prompt: str) -> dict:
        return {"dimension": "test", "score": 85, "evidence_quotes": []}

    async def evaluate_dimension(self, prompt: str) -> DimensionResult:
        return DimensionResult(
            dimension="test", score=85, evidence_quotes=[], model_name=self.model_name
        )


class SchemaRepairProvider(BaseProvider):
    """首次返回结构错误，第二次在纠错提示下成功。"""

    def __init__(self):
        self.model_name = "schema-repair-model"
        self.timeout = 5.0
        self.prompts: list[str] = []

    async def generate_json_response(self, prompt: str) -> dict:
        return {}

    async def evaluate_dimension(self, prompt: str) -> DimensionResult:
        self.prompts.append(prompt)
        if len(self.prompts) == 1:
            raise ProviderResponseValidationError(
                self.model_name,
                "结构化输出校验失败",
                raw_response='{"dimension":"test","score":80}',
                invalid_fields=("evidence_quotes",),
            )
        return DimensionResult(
            dimension="test",
            score=80,
            evidence_quotes=[],
            model_name=self.model_name,
        )


class RuleIdRepairProvider(BaseProvider):
    """首次自造规则编号，收到纠错提示后返回有效编号。"""

    def __init__(self):
        self.model_name = "rule-repair-model"
        self.timeout = 5.0
        self.prompts: list[str] = []

    async def generate_json_response(self, prompt: str) -> dict:
        return {}

    async def evaluate_dimension(self, prompt: str) -> DimensionResult:
        self.prompts.append(prompt)
        rule_id = (
            "analytical_framework.no_operational_framework"
            if len(self.prompts) > 1
            else "analytical_framework.invented_rule"
        )
        return DimensionResult(
            dimension="analytical_framework",
            score=70,
            evidence_quotes=[],
            limit_rule_triggered=[
                LimitRuleTriggered(
                    rule_id=rule_id,
                    rule="测试规则",
                    score_ceiling=50,
                    priority=1,
                    evidence="测试证据",
                )
            ],
            model_name=self.model_name,
        )


@pytest.mark.asyncio
async def test_timeout_returns_error_not_hang():
    """超时 provider 应在 timeout 后返回 ProviderTimeoutError，而非无限等待"""
    provider = SlowProvider(delay=10.0)
    outcome, _, _ = await _call_with_timing(provider, "test prompt", retry_attempts=1)
    assert isinstance(outcome, ProviderTimeoutError)
    assert "slow-model" in str(outcome)


@pytest.mark.asyncio
async def test_timeout_retries_then_fails():
    """超时 provider 重试 3 次后仍返回 ProviderTimeoutError"""
    provider = SlowProvider(delay=10.0)
    outcome, _, _ = await _call_with_timing(provider, "test prompt", retry_attempts=3)
    assert isinstance(outcome, ProviderTimeoutError)


@pytest.mark.asyncio
async def test_fast_provider_succeeds():
    """正常 provider 不受 timeout 机制影响"""
    provider = FastProvider()
    outcome, _, _ = await _call_with_timing(provider, "test prompt")
    assert isinstance(outcome, DimensionResult)
    assert outcome.score == 85


@pytest.mark.asyncio
async def test_timeout_does_not_block_other_providers():
    """并发场景：一个 provider 超时不阻塞其他 provider"""
    slow = SlowProvider(delay=10.0)
    fast = FastProvider()

    results = await asyncio.gather(
        _call_with_timing(slow, "prompt", retry_attempts=1),
        _call_with_timing(fast, "prompt", retry_attempts=1),
    )

    slow_outcome, _, _ = results[0]
    fast_outcome, _, _ = results[1]

    assert isinstance(slow_outcome, ProviderTimeoutError)
    assert isinstance(fast_outcome, DimensionResult)
    assert fast_outcome.score == 85


@pytest.mark.asyncio
async def test_provider_timeout_error_attributes():
    """ProviderTimeoutError 携带正确的 provider 名和 timeout 值"""
    err = ProviderTimeoutError("glm-5.1", 90.0)
    assert err.provider == "glm-5.1"
    assert err.timeout == 90.0
    assert "90.0s" in str(err)


@pytest.mark.asyncio
async def test_schema_failure_retry_names_invalid_fields():
    provider = SchemaRepairProvider()

    outcome, _, used_prompt = await _call_with_timing(
        provider,
        "original prompt",
        retry_attempts=2,
    )

    assert isinstance(outcome, DimensionResult)
    assert len(provider.prompts) == 2
    assert "evidence_quotes" in provider.prompts[1]
    assert "完整 JSON" in used_prompt


@pytest.mark.asyncio
async def test_unknown_rule_id_retries_with_allowed_ids():
    provider = RuleIdRepairProvider()
    dimension = Dimension(
        key="analytical_framework",
        name_zh="理论建构力",
        name_en="Analytical Framework",
        weight=0.15,
        prompt_template="评价论文",
        ceiling_rules=[
            {
                "rule_id": "analytical_framework.no_operational_framework",
                "score_ceiling": 50,
            }
        ],
    )

    outcome, _, used_prompt = await _call_with_timing(
        provider,
        "original prompt",
        dimension_key=dimension.key,
        dimension=dimension,
        retry_attempts=2,
    )

    assert isinstance(outcome, DimensionResult)
    assert outcome.score == 50
    assert len(provider.prompts) == 2
    assert "analytical_framework.no_operational_framework" in used_prompt
