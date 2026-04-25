from src.evaluation.providers.factory import create_providers
from src.evaluation.providers.openrouter_provider import OpenRouterProvider


def test_create_providers_supports_openrouter_gpt_5_4():
    providers = create_providers(["gpt-5.4-openrouter"])

    assert len(providers) == 1
    assert isinstance(providers[0], OpenRouterProvider)
    assert providers[0].model_name == "openai/gpt-5.4"
