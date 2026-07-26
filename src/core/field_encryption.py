from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from src.core.config import settings


def _fernet() -> Fernet:
    digest = hashlib.sha256(settings.field_encryption_key.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_field(value: str) -> str:
    """加密需要短期或长期落库的安全字段。"""

    return _fernet().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_field(value: str) -> str:
    """解密安全字段；密钥不匹配时使用统一错误避免泄漏内部信息。"""

    try:
        return _fernet().decrypt(value.encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("安全字段无法解密") from exc
