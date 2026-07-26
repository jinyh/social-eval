from src.editorial.position import resolve_position_providers
from src.evaluation.providers.base import BaseProvider
from src.evaluation.schemas import DimensionResult


class _Provider(BaseProvider):
    def __init__(self, model_name: str) -> None:
        self.model_name = model_name

    async def evaluate_dimension(self, prompt: str) -> DimensionResult:
        raise NotImplementedError


def test_position_models_are_completed_independently_from_candidate_six_dimension_set():
    six_dimension_providers = [
        _Provider("glm-5.2"),
        _Provider("qwen3.7-max-2026-06-08"),
        _Provider("deepseek-v4-pro"),
        _Provider("kimi-k2.6"),
    ]
    requested: list[list[str]] = []

    def provider_factory(names: list[str]) -> list[BaseProvider]:
        requested.append(names)
        return [_Provider(name) for name in names]

    providers = resolve_position_providers(
        six_dimension_providers,
        provider_factory,
    )

    assert [provider.model_name for provider in providers] == [
        "deepseek-v4-pro",
        "qwen3.6-plus",
    ]
    assert providers[0] is six_dimension_providers[2]
    assert requested == [["qwen3.6-plus"]]
