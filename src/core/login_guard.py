from __future__ import annotations

import hashlib

from redis import Redis
from redis.exceptions import RedisError

from src.core.config import settings


class LoginGuardUnavailable(RuntimeError):
    """生产登录限流依赖不可用。"""


def _client() -> Redis:
    return Redis.from_url(
        settings.redis_url,
        socket_connect_timeout=2,
        socket_timeout=2,
        decode_responses=True,
    )


def _key(client_ip: str, email: str) -> str:
    identity = f"{client_ip}|{email.strip().lower()}".encode()
    return f"socialeval:login:{hashlib.sha256(identity).hexdigest()}"


def register_failed_login(client_ip: str, email: str) -> tuple[int, int]:
    """登记失败并返回当前次数和窗口秒数；生产中 Redis 故障时拒绝放行。"""

    try:
        client = _client()
        key = _key(client_ip, email)
        count = int(client.incr(key))
        if count == 1:
            client.expire(key, settings.login_window_seconds)
        ttl = max(int(client.ttl(key)), 1)
        return count, ttl
    except RedisError as exc:
        raise LoginGuardUnavailable("登录保护服务暂不可用") from exc


def clear_failed_logins(client_ip: str, email: str) -> None:
    try:
        _client().delete(_key(client_ip, email))
    except RedisError as exc:
        raise LoginGuardUnavailable("登录保护服务暂不可用") from exc


def register_security_failure(scope: str, identity: str) -> tuple[int, int]:
    """为重置、双因素等安全流程提供统一 Redis 限速。"""

    digest = hashlib.sha256(f"{scope}|{identity}".encode()).hexdigest()
    key = f"socialeval:security:{scope}:{digest}"
    try:
        client = _client()
        count = int(client.incr(key))
        if count == 1:
            client.expire(key, settings.security_window_seconds)
        return count, max(int(client.ttl(key)), 1)
    except RedisError as exc:
        raise LoginGuardUnavailable("安全校验服务暂不可用") from exc
