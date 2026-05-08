"""KETAN Provider 测试"""
from types import SimpleNamespace

from src.evaluation.providers import ketan_provider
from src.evaluation.providers.ketan_provider import KetanProvider


def test_ketan_provider_initialization():
    """测试 KETAN provider 初始化"""
    provider = KetanProvider("gpt-5.5")
    assert provider.model_name == "gpt-5.5"


def test_ketan_provider_uses_configured_base_url(monkeypatch):
    """测试 KETAN provider 使用配置的 base_url"""
    monkeypatch.setattr(
        ketan_provider,
        "settings",
        SimpleNamespace(
            ketan_api_key="test-key",
            ketan_base_url="https://test.ketan.ai/v1",
        ),
    )
    provider = KetanProvider("gpt-5.5")
    assert str(provider._client.base_url) == "https://test.ketan.ai/v1/"


def test_ketan_provider_uses_configured_api_key(monkeypatch):
    """测试 KETAN provider 使用配置的 API key"""
    monkeypatch.setattr(
        ketan_provider,
        "settings",
        SimpleNamespace(
            ketan_api_key="test-api-key-12345",
            ketan_base_url="https://api.ketan.ai/v1",
        ),
    )
    provider = KetanProvider("gpt-5.5")
    assert provider._client.api_key == "test-api-key-12345"
