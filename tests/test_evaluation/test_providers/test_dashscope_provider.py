from types import SimpleNamespace

import pytest

from src.core.exceptions import ProviderResponseValidationError
from src.evaluation.providers import dashscope_provider
from src.evaluation.providers.dashscope_provider import DashScopeProvider


class _FakeCompletions:
    def __init__(self):
        self.last_request = None

    async def create(self, **kwargs):
        self.last_request = kwargs
        message = SimpleNamespace(
            content='{"dimension":"analytical_framework","score":82}'
        )
        return SimpleNamespace(
            choices=[SimpleNamespace(message=message, finish_reason="stop")],
            usage=SimpleNamespace(completion_tokens=32),
        )


def _fake_client():
    completions = _FakeCompletions()
    return SimpleNamespace(
        chat=SimpleNamespace(completions=completions),
    )


@pytest.mark.asyncio
async def test_schema_validation_error_preserves_raw_response(monkeypatch):
    monkeypatch.setattr(
        dashscope_provider.openai,
        "AsyncOpenAI",
        lambda **kwargs: _fake_client(),
    )
    provider = DashScopeProvider("qwen3.7-max-2026-06-08")

    with pytest.raises(ProviderResponseValidationError) as exc_info:
        await provider.evaluate_dimension("prompt")

    error = exc_info.value
    assert error.invalid_fields == ("evidence_quotes",)
    assert '"score": 82' in error.raw_response
    assert "finish_reason=stop" in str(error)
    assert "completion_tokens=32" in str(error)


@pytest.mark.asyncio
async def test_candidate_generation_parameters_are_forwarded(monkeypatch):
    client = _fake_client()
    monkeypatch.setattr(
        dashscope_provider.openai,
        "AsyncOpenAI",
        lambda **kwargs: client,
    )
    provider = DashScopeProvider(
        "qwen3.7-max-2026-06-08",
        extra_body={"enable_thinking": True, "thinking_budget": 4096},
        max_completion_tokens=8192,
    )

    await provider.generate_json_response("prompt")

    request = client.chat.completions.last_request
    assert request["extra_body"]["thinking_budget"] == 4096
    assert request["max_completion_tokens"] == 8192
