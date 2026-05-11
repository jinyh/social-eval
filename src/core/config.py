from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql://socialeval:socialeval@localhost:5432/socialeval"
    redis_url: str = "redis://localhost:6379/0"
    secret_key: str = "change-me-in-production"
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    deepseek_api_key: str = ""
    zenmux_api_key: str = ""
    zenmux_base_url: str = "https://zenmux.ai/api/v1"
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    dashscope_api_key: str = ""
    dashscope_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    ketan_api_key: str = ""
    ketan_base_url: str = "https://api.ketan.ai/v1"
    fucheers_api_key: str = Field(default="", validation_alias="FUCHEERS_API_KEY")
    fucheers_base_url: str = Field(
        default="https://api.fucheers.ai/v1",
        validation_alias=AliasChoices("FUCHEERS_BASE_URL", "FUCHEERS_BASW_URL"),
    )
    yunyi_api_key: str = ""
    yunyi_base_url: str = "https://api.yunyi.ai/v1"
    sss_api_key: str = ""
    sss_base_url: str = "https://api.sss.ai/v1"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "noreply@socialeval.local"
    max_concurrent_models: int = 3
    default_std_threshold: float = 5.0
    allowed_origins: str = ""
    provider_timeout: float = 120.0

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        populate_by_name=True,
    )


settings = Settings()
