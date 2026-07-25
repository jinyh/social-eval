from src.evaluation.providers.factory import create_providers
from src.evaluation.providers.dashscope_provider import DashScopeProvider
from src.evaluation.providers.fucheers_provider import FucheersProvider
from src.evaluation.providers.ketan_provider import KetanProvider
from src.evaluation.providers.openrouter_provider import OpenRouterProvider


def test_create_providers_supports_openrouter_gpt_5_4():
    providers = create_providers(["gpt-5.4-openrouter"])

    assert len(providers) == 1
    assert isinstance(providers[0], OpenRouterProvider)
    assert providers[0].model_name == "openai/gpt-5.4"


def test_create_providers_routes_gpt_5_5_to_fucheers():
    """测试工厂默认用 FUCHEERS 创建 GPT-5.5 provider"""
    providers = create_providers(["gpt-5.5"])
    assert len(providers) == 1
    assert isinstance(providers[0], FucheersProvider)
    assert providers[0].model_name == "gpt-5.5"


def test_create_providers_supports_fucheers_alias():
    """测试工厂支持 FUCHEERS 显式别名"""
    providers = create_providers(["fucheers-gpt-5.5"])
    assert len(providers) == 1
    assert isinstance(providers[0], FucheersProvider)
    assert providers[0].model_name == "gpt-5.5"


def test_create_providers_supports_ketan_alias():
    """测试工厂支持 KETAN 别名"""
    providers = create_providers(["ketan-gpt-5.5"])
    assert len(providers) == 1
    assert isinstance(providers[0], KetanProvider)
    assert providers[0].model_name == "gpt-5.5"


def test_qwen_upgrade_candidate_has_frozen_generation_parameters():
    provider = create_providers(["qwen3.7-max-2026-06-08"])[0]

    assert isinstance(provider, DashScopeProvider)
    assert provider.extra_body == {
        "enable_thinking": True,
        "thinking_budget": 4096,
    }
    assert provider.max_completion_tokens == 8192
    assert provider.timeout == 240.0


def test_glm_upgrade_candidate_has_extended_timeout():
    provider = create_providers(["glm-5.2"])[0]

    assert isinstance(provider, DashScopeProvider)
    assert provider.timeout == 240.0
