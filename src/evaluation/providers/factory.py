from src.evaluation.providers.base import BaseProvider

# 延迟 import 注册表：(module_path, class_name, init_args)
# 只在 create_providers 被调用时才 import 对应模块，
# 避免 import anthropic/openai 等 SDK 在模块加载时卡住。
_PROVIDER_REGISTRY: dict[str, tuple[str, str, tuple]] = {
    # 国外模型
    "openai": ("src.evaluation.providers.openai_provider", "OpenAIProvider", ()),
    "anthropic": (
        "src.evaluation.providers.anthropic_provider",
        "AnthropicProvider",
        (),
    ),
    "deepseek": ("src.evaluation.providers.deepseek_provider", "DeepSeekProvider", ()),
    # Zenmux
    "gpt-5.4": (
        "src.evaluation.providers.zenmux_provider",
        "ZenmuxProvider",
        ("gpt-5.4",),
    ),
    "gemini-3.1-pro": (
        "src.evaluation.providers.zenmux_provider",
        "ZenmuxProvider",
        ("google/gemini-3.1-pro",),
    ),
    "claude-sonnet-4-6": (
        "src.evaluation.providers.zenmux_provider",
        "ZenmuxProvider",
        ("anthropic/claude-sonnet-4-6",),
    ),
    # OpenRouter
    "gpt-5.4-openrouter": (
        "src.evaluation.providers.openrouter_provider",
        "OpenRouterProvider",
        ("openai/gpt-5.4",),
    ),
    "openrouter-gpt-5.4": (
        "src.evaluation.providers.openrouter_provider",
        "OpenRouterProvider",
        ("openai/gpt-5.4",),
    ),
    # 国内模型：DashScope 百炼
    "kimi-k2.6": (
        "src.evaluation.providers.dashscope_provider",
        "DashScopeProvider",
        ("kimi-k2.6",),
    ),
    "qwen3.6-plus": (
        "src.evaluation.providers.dashscope_provider",
        "DashScopeProvider",
        ("qwen3.6-plus",),
    ),
    "qwen3.7-max": (
        "src.evaluation.providers.dashscope_provider",
        "DashScopeProvider",
        ("qwen3.7-max",),
    ),
    "qwen3.7-max-2026-06-08": (
        "src.evaluation.providers.dashscope_provider",
        "DashScopeProvider",
        ("qwen3.7-max-2026-06-08",),
        {
            "temperature": 0.3,
            "extra_body": {
                "enable_thinking": True,
                "thinking_budget": 4096,
            },
            "max_completion_tokens": 8192,
        },
    ),
    "glm-5.1": (
        "src.evaluation.providers.dashscope_provider",
        "DashScopeProvider",
        ("glm-5.1",),
    ),
    "glm-5.2": (
        "src.evaluation.providers.dashscope_provider",
        "DashScopeProvider",
        ("glm-5.2",),
        {"temperature": 0.3},
    ),
    "deepseek-v4-pro": (
        "src.evaluation.providers.dashscope_provider",
        "DashScopeProvider",
        ("deepseek-v4-pro",),
    ),
    # FUCHEERS
    "gpt-5.5": (
        "src.evaluation.providers.fucheers_provider",
        "FucheersProvider",
        ("gpt-5.5",),
    ),
    "gpt-5.5-high": (
        "src.evaluation.providers.fucheers_provider",
        "FucheersProvider",
        ("gpt-5.5",),
        {"reasoning_effort": "high"},
    ),
    "fucheers-gpt-5.5": (
        "src.evaluation.providers.fucheers_provider",
        "FucheersProvider",
        ("gpt-5.5",),
    ),
    # KETAN
    "ketan-gpt-5.5": (
        "src.evaluation.providers.ketan_provider",
        "KetanProvider",
        ("gpt-5.5",),
    ),
    # YUNYI
    "yunyi-gpt-5.5": (
        "src.evaluation.providers.yunyi_provider",
        "YunyiProvider",
        ("gpt-5.5",),
    ),
    # SSS
    "sss-gpt-5.5": (
        "src.evaluation.providers.sss_provider",
        "SSSProvider",
        ("gpt-5.5",),
    ),
}


def _resolve_provider(name: str) -> BaseProvider:
    """按名称延迟 import 并实例化对应 Provider"""
    entry = _PROVIDER_REGISTRY.get(name)
    if not entry:
        raise ValueError(f"未知 Provider：{name}")

    if len(entry) == 4:
        module_path, class_name, args, kwargs = entry
    else:
        module_path, class_name, args = entry
        kwargs = {}

    import importlib

    module = importlib.import_module(module_path)
    cls = getattr(module, class_name)
    return cls(*args, **kwargs)


def create_providers(names: list[str]) -> list[BaseProvider]:
    providers = []
    for name in names:
        providers.append(_resolve_provider(name))
    return providers
