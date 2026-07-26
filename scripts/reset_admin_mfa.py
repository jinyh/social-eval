from __future__ import annotations

import argparse

from src.api.auth.account import invalidate_user_sessions, revoke_user_api_keys
from src.core.audit import record_audit_log
from src.core.database import SessionLocal
from src.models.user import MfaRecoveryCode, User


def main() -> None:
    """在管理员丢失认证器和恢复码时安全地重置双因素认证。"""

    parser = argparse.ArgumentParser(description="紧急重置指定生产管理员的双因素认证")
    parser.add_argument("--email", required=True)
    args = parser.parse_args()
    email = args.email.strip().lower()

    confirmation = input(f"请输入管理员邮箱 {email} 以确认重置: ").strip().lower()
    if confirmation != email:
        raise SystemExit("确认内容不匹配，未执行任何修改")

    db = SessionLocal()
    try:
        user = (
            db.query(User)
            .filter(
                User.email == email,
                User.role == "admin",
                User.is_active.is_(True),
            )
            .first()
        )
        if user is None:
            raise SystemExit("未找到该有效管理员")

        user.mfa_secret_encrypted = None
        user.mfa_enabled_at = None
        invalidate_user_sessions(user)
        revoked = revoke_user_api_keys(db, user.id)
        recovery_codes_deleted = (
            db.query(MfaRecoveryCode)
            .filter(MfaRecoveryCode.user_id == user.id)
            .delete()
        )
        db.add(user)
        db.commit()
        record_audit_log(
            db,
            actor_id=None,
            object_type="user",
            object_id=user.id,
            action="admin_mfa_emergency_reset",
            result="success",
            details={
                "api_keys_revoked": revoked,
                "recovery_codes_deleted": recovery_codes_deleted,
            },
        )
        print("双因素认证已重置；所有会话和 API Key 已失效，下次登录必须重新绑定。")
    finally:
        db.close()


if __name__ == "__main__":
    main()
