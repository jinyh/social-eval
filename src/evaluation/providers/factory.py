from src.evaluation.providers.base import BaseProvider
from src.evaluation.providers.openai_provider import OpenAIProvider
from src.evaluation.providers.anthropic_provider import AnthropicProvider
from src.evaluation.providers.deepseek_provider import DeepSeekProvider
from src.evaluation.providers.zenmux_provider import ZenmuxProvider

_PROVIDER_MAP: dict[str, type[BaseProvider] | type] = {
    "openai": OpenAIProvider,
    "anthropic": AnthropicProvider,
    "deepseek": DeepSeekProvider,
    "gpt-5.4": lambda: ZenmuxProvider("gpt-5.4"),
    "kimi-k2.6": lambda: ZenmuxProvider("moonshotai/kimi-k2.6"),
    "glm-5.1": lambda: ZenmuxProvider("z-ai/glm-5.1"),
    "qwen3.6-plus": lambda: ZenmuxProvider("qwen/qwen3.6-plus"),
}


def create_providers(names: list[str]) -> list[BaseProvider]:
    providers = []
    for name in names:
        entry = _PROVIDER_MAP.get(name)
        if not entry:
            raise ValueError(f"未知 Provider：{name}")
        if callable(entry) and not isinstance(entry, type):
            providers.append(entry())
        else:
            providers.append(entry())
    return providers
