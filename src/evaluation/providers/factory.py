from src.evaluation.providers.base import BaseProvider
from src.evaluation.providers.openai_provider import OpenAIProvider
from src.evaluation.providers.anthropic_provider import AnthropicProvider
from src.evaluation.providers.deepseek_provider import DeepSeekProvider

_PROVIDER_MAP: dict[str, type[BaseProvider]] = {
    "openai": OpenAIProvider,
    "anthropic": AnthropicProvider,
    "deepseek": DeepSeekProvider,
}


def create_providers(names: list[str]) -> list[BaseProvider]:
    providers = []
    for name in names:
        cls = _PROVIDER_MAP.get(name)
        if not cls:
            raise ValueError(f"未知 Provider：{name}")
        providers.append(cls())
    return providers
