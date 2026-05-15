"""FUCHEERS Provider 测试"""
from types import SimpleNamespace

from src.evaluation.providers import fucheers_provider
from src.evaluation.providers.fucheers_provider import FucheersProvider


def test_fucheers_provider_initialization():
    """测试 FUCHEERS provider 初始化"""
    provider = FucheersProvider("gpt-5.5")
    assert provider.model_name == "gpt-5.5"


def test_fucheers_provider_uses_configured_base_url(monkeypatch):
    """测试 FUCHEERS provider 使用配置的 base_url"""
    monkeypatch.setattr(
        fucheers_provider,
        "settings",
        SimpleNamespace(
            fucheers_api_key="test-key",
            fucheers_base_url="https://test.fucheers.ai/v1",
        ),
    )
    provider = FucheersProvider("gpt-5.5")
    assert str(provider._client.base_url) == "https://test.fucheers.ai/v1/"


def test_fucheers_provider_uses_configured_api_key(monkeypatch):
    """测试 FUCHEERS provider 使用配置的 API key"""
    monkeypatch.setattr(
        fucheers_provider,
        "settings",
        SimpleNamespace(
            fucheers_api_key="test-api-key-12345",
            fucheers_base_url="https://api.fucheers.ai/v1",
        ),
    )
    provider = FucheersProvider("gpt-5.5")
    assert provider._client.api_key == "test-api-key-12345"
