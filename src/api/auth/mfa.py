from __future__ import annotations

import hashlib
import secrets
from io import BytesIO

import pyotp
import qrcode
import qrcode.image.svg
from sqlalchemy.orm import Session

from src.core.field_encryption import decrypt_field, encrypt_field
from src.core.time import utc_now
from src.models.user import MfaRecoveryCode, User


def create_totp_setup(user: User) -> tuple[str, str, str]:
    """创建待确认的 TOTP 密钥、配置 URI 和本地生成的 SVG。"""

    secret = pyotp.random_base32()
    user.mfa_secret_encrypted = encrypt_field(secret)
    uri = pyotp.TOTP(secret).provisioning_uri(
        name=user.email,
        issuer_name="文科论文智能辅助评审系统",
    )
    output = BytesIO()
    qrcode.make(uri, image_factory=qrcode.image.svg.SvgPathImage).save(output)
    return secret, uri, output.getvalue().decode("utf-8")


def verify_totp(user: User, code: str) -> bool:
    if not user.mfa_secret_encrypted:
        return False
    secret = decrypt_field(user.mfa_secret_encrypted)
    return bool(pyotp.TOTP(secret).verify(code.strip(), valid_window=1))


def _hash_recovery_code(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def replace_recovery_codes(db: Session, user: User) -> list[str]:
    db.query(MfaRecoveryCode).filter(MfaRecoveryCode.user_id == user.id).delete()
    raw_codes = [secrets.token_hex(6).upper() for _ in range(10)]
    db.add_all(
        MfaRecoveryCode(user_id=user.id, code_hash=_hash_recovery_code(code))
        for code in raw_codes
    )
    return raw_codes


def consume_recovery_code(db: Session, user: User, code: str) -> bool:
    candidate_hash = _hash_recovery_code(code.strip().upper())
    row = (
        db.query(MfaRecoveryCode)
        .filter(
            MfaRecoveryCode.user_id == user.id,
            MfaRecoveryCode.code_hash == candidate_hash,
            MfaRecoveryCode.used_at.is_(None),
        )
        .first()
    )
    if row is None:
        return False
    row.used_at = utc_now()
    db.add(row)
    return True
