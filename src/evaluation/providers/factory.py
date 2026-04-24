from src.evaluation.providers.base import BaseProvider
from src.evaluation.providers.openai_provider import OpenAIProvider
from src.evaluation.providers.anthropic_provider import AnthropicProvider
from src.evaluation.providers.deepseek_provider import DeepSeekProvider
from src.evaluation.providers.zenmux_provider import ZenmuxProvider
from src.evaluation.providers.dashscope_provider import DashScopeProvider

_PROVIDER_MAP: dict[str, type[BaseProvider] | type] = {
    # 国外模型：通过 Zenmux 调用
    "openai": OpenAIProvider,
    "anthropic": AnthropicProvider,
    "deepseek": DeepSeekProvider,
    "gpt-5.4": lambda: ZenmuxProvider("gpt-5.4"),
    "gemini-3.1-pro": lambda: ZenmuxProvider("google/gemini-3.1-pro"),
    "claude-sonnet-4-6": lambda: ZenmuxProvider("anthropic/claude-sonnet-4-6"),
    # 国内模型：通过 DashScope 百炼调用
    "kimi-k2.6": lambda: DashScopeProvider("kimi-k2.6"),
    "qwen3.6-plus": lambda: DashScopeProvider("qwen3.6-plus"),
    "glm-5.1": lambda: DashScopeProvider("glm-5.1"),
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
