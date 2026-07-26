from __future__ import annotations

from src.core.config import settings


def production_config_errors() -> list[str]:
    """返回生产配置错误，不读取数据库或输出任何凭据值。"""

    errors = []
    if (
        settings.secret_key == "change-me-in-production"
        or "replace-with" in settings.secret_key.lower()
        or len(settings.secret_key) < 32
    ):
        errors.append("SECRET_KEY 必须至少 32 个字符且不能使用默认值")
    if not settings.allowed_hosts:
        errors.append("必须配置 ALLOWED_HOSTS")
    if not settings.allowed_origins:
        errors.append("必须配置 ALLOWED_ORIGINS")
    if not settings.session_https_only:
        errors.append("SESSION_HTTPS_ONLY 必须为 true")
    if not settings.public_base_url.startswith("https://"):
        errors.append("PUBLIC_BASE_URL 必须使用 https")
    if (
        "localhost" in settings.public_base_url
        or "127.0.0.1" in settings.public_base_url
    ):
        errors.append("PUBLIC_BASE_URL 不能使用本机地址")
    if (
        settings.field_encryption_key == "development-field-encryption-key"
        or "replace-with" in settings.field_encryption_key.lower()
        or len(settings.field_encryption_key) < 32
    ):
        errors.append("FIELD_ENCRYPTION_KEY 必须至少 32 个字符且不能使用默认值")
    if not settings.admin_mfa_required:
        errors.append("ADMIN_MFA_REQUIRED 必须为 true")
    if not settings.email_enabled:
        errors.append("EMAIL_ENABLED 必须为 true")
    if settings.email_enabled and (not settings.smtp_host or not settings.smtp_from):
        errors.append("启用邮件后必须配置 SMTP_HOST 和 SMTP_FROM")
    if settings.smtp_ssl and settings.smtp_starttls:
        errors.append("SMTP_SSL 与 SMTP_STARTTLS 不能同时启用")
    return errors
