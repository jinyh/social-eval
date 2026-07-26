from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    public_base_url: str = "http://localhost:5173"
    database_url: str = "postgresql://socialeval:socialeval@localhost:5432/socialeval"
    redis_url: str = "redis://localhost:6379/0"
    secret_key: str = "change-me-in-production"
    field_encryption_key: str = "development-field-encryption-key"
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
    smtp_from_name: str = "文科论文智能辅助评审系统"
    smtp_starttls: bool = True
    smtp_ssl: bool = False
    smtp_timeout: float = 10.0
    email_enabled: bool = False
    max_concurrent_models: int = 3
    default_std_threshold: float = 5.0
    allowed_origins: str = ""
    allowed_hosts: str = ""
    session_https_only: bool = False
    provider_timeout: float = 120.0
    upload_max_bytes: int = 30 * 1024 * 1024
    task_stale_seconds: int = 600
    login_max_attempts: int = 5
    login_window_seconds: int = 900
    session_max_age_seconds: int = 12 * 60 * 60
    password_reset_ttl_seconds: int = 30 * 60
    invitation_ttl_days: int = 7
    security_max_attempts: int = 5
    security_window_seconds: int = 600
    retention_manuscript_days: int = 365
    retention_audit_days: int = 3 * 365
    admin_mfa_required: bool = False

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        populate_by_name=True,
    )


settings = Settings()
