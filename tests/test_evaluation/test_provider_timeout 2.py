"""测试 provider 超时机制：确保超时不会挂死 pipeline，而是走降级路径。"""

import asyncio

import pytest

from src.core.exceptions import ProviderTimeoutError
from src.evaluation.concurrent_evaluator import _call_with_timing
from src.evaluation.providers.base import BaseProvider
from src.evaluation.schemas import DimensionResult


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
