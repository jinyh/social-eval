from passlib.context import CryptContext


MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_LENGTH = 128
_PWD_CONTEXT = CryptContext(
    schemes=["argon2", "pbkdf2_sha256"],
    deprecated=["pbkdf2_sha256"],
)


def validate_password(password: str) -> None:
    """执行统一密码长度规则，不采用妨碍长口令的字符组合限制。"""

    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"密码至少需要 {MIN_PASSWORD_LENGTH} 个字符")
    if len(password) > MAX_PASSWORD_LENGTH:
        raise ValueError(f"密码不能超过 {MAX_PASSWORD_LENGTH} 个字符")


def hash_password(password: str) -> str:
    validate_password(password)
    return _PWD_CONTEXT.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return _PWD_CONTEXT.verify(plain_password, hashed_password)


def verify_and_update_password(
    plain_password: str, hashed_password: str
) -> tuple[bool, str | None]:
    """验证密码，并在旧摘要算法命中时返回新的 Argon2id 摘要。"""

    return _PWD_CONTEXT.verify_and_update(plain_password, hashed_password)
