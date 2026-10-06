"""Seed vai trò, quyền mặc định và tài khoản Admin đầu tiên.

    python -m scripts.seed

Chạy một lần sau `alembic upgrade head`. Idempotent: chạy lại không nhân đôi.
Ma trận quyền lấy từ app/enums.py:DEFAULT_ROLE_PERMISSIONS - sửa ở đó, không sửa
ở đây.
"""

from __future__ import annotations

import getpass
import sys

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.config import settings
from app.enums import DEFAULT_ROLE_PERMISSIONS, RoleCode
from app.models import Role, RolePermission, User

ROLE_NAMES = {
    RoleCode.ADMIN: ("Administrator", "管理者"),
    RoleCode.GA_MANAGER: ("GA Manager", "総務課長"),
    RoleCode.EXECUTIVE: ("Executive", "役員"),
}


def seed(db: Session) -> None:
    roles: dict[RoleCode, Role] = {}
    for code, (en, ja) in ROLE_NAMES.items():
        role = db.scalar(select(Role).where(Role.code == code.value))
        if role is None:
            role = Role(code=code.value, name_en=en, name_ja=ja)
            db.add(role)
            db.flush()
        roles[code] = role

    for code, modules in DEFAULT_ROLE_PERMISSIONS.items():
        role = roles[code]
        existing = {
            (p.module, p.action)
            for p in db.scalars(
                select(RolePermission).where(RolePermission.role_id == role.id)
            )
        }
        for module, actions in modules.items():
            for action in actions:
                if (module.value, action.value) not in existing:
                    db.add(
                        RolePermission(
                            role_id=role.id, module=module.value, action=action.value
                        )
                    )

    if db.scalar(select(User).where(User.username == "it.admin")) is None:
        pw = getpass.getpass("Mật khẩu cho tài khoản it.admin: ")
        pw2 = getpass.getpass("Nhập lại: ")
        if pw != pw2 or len(pw) < 12:
            sys.exit("Mật khẩu không khớp hoặc ngắn hơn 12 ký tự.")
        from argon2 import PasswordHasher

        db.add(
            User(
                username="it.admin",
                password_hash=PasswordHasher().hash(pw),
                display_name="IT Administrator",
                role_id=roles[RoleCode.ADMIN].id,
                preferred_lang="en",
            )
        )
    db.commit()
    print("Seed xong.")


if __name__ == "__main__":
    with Session(create_engine(settings.database_url)) as s:
        seed(s)
