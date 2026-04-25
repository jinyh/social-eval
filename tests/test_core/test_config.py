from src.core.config import Settings


def test_settings_exposes_zenmux_base_url():
    settings = Settings(
        zenmux_api_key="test-key",
        zenmux_base_url="https://example.invalid/api/v1",
    )

    assert settings.zenmux_base_url == "https://example.invalid/api/v1"


def test_settings_exposes_openrouter_base_url():
    settings = Settings(
        openrouter_api_key="test-key",
        openrouter_base_url="https://openrouter.example/api/v1",
    )

    assert settings.openrouter_base_url == "https://openrouter.example/api/v1"
