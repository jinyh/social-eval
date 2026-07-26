from __future__ import annotations

from sqlalchemy.orm import Session

from src.models.api_key import ApiKey
from src.models.user import User


def revoke_user_api_keys(db: Session, user_id: str) -> int:
    """撤销用户的全部有效 API Key，返回撤销数量。"""

    rows = (
        db.query(ApiKey)
        .filter(ApiKey.user_id == user_id, ApiKey.is_active.is_(True))
        .all()
    )
    for row in rows:
        row.is_active = False
        db.add(row)
    return len(rows)


def invalidate_user_sessions(user: User) -> None:
    """通过版本号使已经签发的客户端 Session 立即失效。"""

    user.session_version += 1
