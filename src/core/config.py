from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql://socialeval:socialeval@localhost:5432/socialeval"
    redis_url: str = "redis://localhost:6379/0"
    secret_key: str = "change-me-in-production"
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    deepseek_api_key: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "noreply@socialeval.local"
    max_concurrent_models: int = 3
    default_std_threshold: float = 5.0

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
