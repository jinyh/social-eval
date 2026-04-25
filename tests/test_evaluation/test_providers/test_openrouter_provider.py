from types import SimpleNamespace

from src.evaluation.providers import openrouter_provider
from src.evaluation.providers.openrouter_provider import OpenRouterProvider


def test_openrouter_provider_uses_configured_base_url(monkeypatch):
    monkeypatch.setattr(
        openrouter_provider,
        "settings",
        SimpleNamespace(
            openrouter_api_key="test-key",
            openrouter_base_url="https://openrouter.example/api/v1",
        ),
    )

    provider = OpenRouterProvider("openai/gpt-5.4")

    assert str(provider._client.base_url) == "https://openrouter.example/api/v1/"
