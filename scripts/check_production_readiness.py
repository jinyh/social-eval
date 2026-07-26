from __future__ import annotations

import os
from urllib.parse import urlparse

from src.core.config import settings
from src.core.production import production_config_errors


def main() -> None:
    errors = list(production_config_errors())
    public_url = urlparse(settings.public_base_url)
    if settings.app_env != "production":
        errors.append("APP_ENV 必须为 production")
    if os.environ.get("APP_DOMAIN", "").strip() != public_url.hostname:
        errors.append("APP_DOMAIN 必须与 PUBLIC_BASE_URL 主机名一致")
    if not public_url.hostname:
        errors.append("PUBLIC_BASE_URL 缺少有效主机名")
    allowed_hosts = {
        item.strip() for item in settings.allowed_hosts.split(",") if item.strip()
    }
    if public_url.hostname and public_url.hostname not in allowed_hosts:
        errors.append("PUBLIC_BASE_URL 主机名必须包含在 ALLOWED_HOSTS 中")
    allowed_origins = {
        item.strip().rstrip("/")
        for item in settings.allowed_origins.split(",")
        if item.strip()
    }
    public_origin = f"{public_url.scheme}://{public_url.netloc}".rstrip("/")
    if public_origin not in allowed_origins:
        errors.append("PUBLIC_BASE_URL 来源必须包含在 ALLOWED_ORIGINS 中")
    if settings.session_max_age_seconds > 12 * 60 * 60:
        errors.append("SESSION_MAX_AGE_SECONDS 不能超过 12 小时")
    if errors:
        print("生产配置检查失败：")
        for error in errors:
            print(f"- {error}")
        raise SystemExit(1)
    print("生产配置检查通过；未输出任何凭据值。")


if __name__ == "__main__":
    main()
