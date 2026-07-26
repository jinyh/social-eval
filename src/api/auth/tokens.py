from __future__ import annotations

import hashlib
import hmac
import secrets


def create_one_time_token() -> tuple[str, str]:
    raw = secrets.token_urlsafe(32)
    return raw, hash_one_time_token(raw)


def hash_one_time_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def token_matches(raw: str, expected_hash: str) -> bool:
    return hmac.compare_digest(hash_one_time_token(raw), expected_hash)
