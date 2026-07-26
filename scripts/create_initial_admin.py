from __future__ import annotations

import argparse
import getpass

from src.api.auth.password import hash_password
from src.core.database import SessionLocal
from src.core.time import utc_now
from src.models.user import User


def main() -> None:
    parser = argparse.ArgumentParser(description="交互式创建首个生产管理员")
    parser.add_argument("--email", required=True)
    parser.add_argument("--display-name", required=True)
    args = parser.parse_args()

    email = args.email.strip().lower()
    password = getpass.getpass("管理员密码（至少 12 个字符）: ")
    confirmation = getpass.getpass("再次输入管理员密码: ")
    if password != confirmation:
        raise SystemExit("两次输入的密码不一致")

    db = SessionLocal()
    try:
        if db.query(User).filter(User.role == "admin").first() is not None:
            raise SystemExit("数据库中已经存在管理员，拒绝再次执行初始化")
        if db.query(User).filter(User.email == email).first() is not None:
            raise SystemExit("该邮箱已经存在用户")
        user = User(
            email=email,
            display_name=args.display_name.strip(),
            hashed_password=hash_password(password),
            role="admin",
            is_active=True,
            password_changed_at=utc_now(),
        )
        db.add(user)
        db.commit()
        print("首个管理员已创建；首次登录必须完成双因素认证。")
    finally:
        db.close()


if __name__ == "__main__":
    main()
