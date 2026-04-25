from types import SimpleNamespace

from src.evaluation.providers import zenmux_provider
from src.evaluation.providers.zenmux_provider import ZenmuxProvider


def test_zenmux_provider_uses_configured_base_url(monkeypatch):
    monkeypatch.setattr(
        zenmux_provider,
        "settings",
        SimpleNamespace(
            zenmux_api_key="test-key",
            zenmux_base_url="https://example.invalid/api/v1",
        ),
    )

    provider = ZenmuxProvider("qwen/qwen3.6-plus")

    assert str(provider._client.base_url) == "https://example.invalid/api/v1/"
