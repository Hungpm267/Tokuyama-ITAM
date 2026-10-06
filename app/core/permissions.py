"""Phân quyền RBAC (Role-Based Access Control) cho hệ thống ITAM.

Mô hình phân quyền theo GEMINI.md:
- users -> roles -> role_permissions (module, action)
- Cộng user_permission_overrides để Admin tinh chỉnh quyền lẻ cho từng cá nhân mà không đổi vai trò.
- MẶC ĐỊNH LÀ TỪ CHỐI (DENY BY DEFAULT).
- Thiếu quyền trả lỗi 403 với thông báo chung. Không tiết lộ thông tin dữ liệu hay cấu trúc.
"""

from __future__ import annotations

from typing import Callable
from fastapi import HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.enums import Module, PermissionAction
from app.models import RolePermission, User, UserPermissionOverride


def has_permission(
    db: Session,
    user: User,
    module: Module | str,
    action: PermissionAction | str,
) -> bool:
    """Kiểm tra xem người dùng có quyền (module, action) hay không.

    Thứ tự ưu tiên:
    1. Kiểm tra tài khoản: phải active và chưa bị xoá mềm.
    2. Kiểm tra user_permission_overrides: nếu có bản ghi ghi đè thì theo cờ `granted`.
    3. Nếu không có ghi đè, kiểm tra role_permissions theo vai trò của người dùng.
    4. Mặc định: từ chối (False).
    """
    if not user or not user.is_active or user.is_deleted:
        return False

    mod_val = module.value if isinstance(module, Module) else str(module)
    act_val = action.value if isinstance(action, PermissionAction) else str(action)

    # 1. Kiểm tra ghi đè cá nhân (Override)
    override = db.scalar(
        select(UserPermissionOverride).where(
            UserPermissionOverride.user_id == user.id,
            UserPermissionOverride.module == mod_val,
            UserPermissionOverride.action == act_val,
        )
    )
    if override is not None:
        return override.granted

    # 2. Kiểm tra quyền của vai trò (Role Permission)
    role_perm = db.scalar(
        select(RolePermission).where(
            RolePermission.role_id == user.role_id,
            RolePermission.module == mod_val,
            RolePermission.action == act_val,
        )
    )
    return role_perm is not None


def get_user_permissions(db: Session, user: User) -> set[tuple[str, str]]:
    """Lấy danh sách tất cả các cặp (module, action) mà người dùng có quyền."""
    if not user or not user.is_active or user.is_deleted:
        return set()

    # Lấy quyền từ role
    role_perms = db.execute(
        select(RolePermission.module, RolePermission.action).where(
            RolePermission.role_id == user.role_id
        )
    ).all()
    perms = {(row.module, row.action) for row in role_perms}

    # Áp dụng overrides
    overrides = db.execute(
        select(
            UserPermissionOverride.module,
            UserPermissionOverride.action,
            UserPermissionOverride.granted,
        ).where(UserPermissionOverride.user_id == user.id)
    ).all()

    for mod, act, granted in overrides:
        if granted:
            perms.add((mod, act))
        else:
            perms.discard((mod, act))

    return perms


def require(
    module: Module | str,
    action: PermissionAction | str,
) -> Callable:
    """FastAPI Dependency để chặn truy cập nếu người dùng không đủ quyền.

    Sử dụng:
        @router.get("/assets", dependencies=[Depends(require(Module.ASSETS, PermissionAction.VIEW))])
        hoặc
        def list_assets(current_user: Annotated[User, Depends(require(Module.ASSETS, PermissionAction.VIEW))]):
    """
    # Import trễ tránh circular dependency với get_current_user / get_db
    from app.core.security import verify_session_token

    def dependency(request: Request) -> User:
        # 1. Lấy thông tin user từ request state hoặc session token cookie
        user: User | None = getattr(request.state, "user", None)
        db: Session | None = getattr(request.state, "db", None)

        # Nếu chưa có trong request state, kiểm tra cookie phiên
        if user is None:
            token = request.cookies.get("itam_session") or request.session.get("token")
            if not token:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Chưa đăng nhập hoặc phiên làm việc đã hết hạn.",
                )
            payload = verify_session_token(token)
            if not payload or "user_id" not in payload:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Phiên làm việc không hợp lệ.",
                )

            # Mở session nếu chưa có
            should_close = False
            if db is None:
                from app.config import settings
                from sqlalchemy import create_engine
                from sqlalchemy.orm import sessionmaker

                engine = getattr(request.app.state, "engine", None)
                if engine is None:
                    engine = create_engine(settings.database_url)
                db = sessionmaker(bind=engine)()
                should_close = True

            try:
                user = db.scalar(
                    select(User).where(
                        User.id == payload["user_id"],
                        User.is_active.is_(True),
                        User.is_deleted.is_(False),
                    )
                )
            finally:
                if should_close:
                    db.close()

        if user is None or not user.is_active or user.is_deleted:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Tài khoản không tồn tại hoặc đã bị vô hiệu hóa.",
            )

        # 2. Kiểm tra quyền
        # Cần database session để tra cứu role_permissions & overrides
        db_session: Session | None = getattr(request.state, "db", None)
        temp_db = False
        if db_session is None:
            from app.config import settings
            from sqlalchemy import create_engine
            from sqlalchemy.orm import sessionmaker

            engine = getattr(request.app.state, "engine", None)
            if engine is None:
                engine = create_engine(settings.database_url)
            db_session = sessionmaker(bind=engine)()
            temp_db = True

        try:
            allowed = has_permission(db_session, user, module, action)
        finally:
            if temp_db:
                db_session.close()

        if not allowed:
            # 403 chung, không tiết lộ chi tiết
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Bạn không có quyền thực hiện thao tác này.",
            )

        return user

    return dependency
