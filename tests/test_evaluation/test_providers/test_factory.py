from src.evaluation.providers.factory import create_providers
from src.evaluation.providers.openrouter_provider import OpenRouterProvider
from src.evaluation.providers.fucheers_provider import FucheersProvider
from src.evaluation.providers.ketan_provider import KetanProvider


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
