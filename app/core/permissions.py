"""Phân quyền RBAC (Role-Based Access Control) cho hệ thống ITAM.

Mô hình phân quyền theo GEMINI.md:
- users -> roles -> role_permissions (module, action)
- Cộng user_permission_overrides để Admin tinh chỉnh quyền lẻ cho từng cá nhân mà không đổi vai trò.
- MẶC ĐỊNH LÀ TỪ CHỐI (DENY BY DEFAULT).
- Thiếu quyền trả lỗi 403 với thông báo chung. Không tiết lộ thông tin dữ liệu hay cấu trúc.
"""

from __future__ import annotations

from typing import Any, Callable
from fastapi import HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.enums import Module, PermissionAction, RoleCode
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
    from fastapi import Depends
    from app.core.security import verify_session_token
    from app.db import get_db

    def dependency(request: Request, db: Session = Depends(get_db)) -> User:
        # 1. Lấy thông tin user từ request state hoặc session token cookie
        user: User | None = getattr(request.state, "user", None)

        if user is None:
            token = request.cookies.get("itam_session")
            if not token and hasattr(request, "session"):
                token = request.session.get("token")
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

            user = db.scalar(
                select(User).where(
                    User.id == payload["user_id"],
                    User.is_active.is_(True),
                    User.is_deleted.is_(False),
                )
            )

        if user is None or not user.is_active or user.is_deleted:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Tài khoản không tồn tại hoặc đã bị vô hiệu hóa.",
            )

        # 2. Kiểm tra quyền
        allowed = has_permission(db, user, module, action)
        if not allowed:
            # 403 chung, không tiết lộ chi tiết
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Bạn không có quyền thực hiện thao tác này.",
            )

        return user

    return dependency


# =============================================================================
# MA TRẬN QUYỀN VAI TRÒ (ROLE-PERMISSION MATRIX)
# =============================================================================

MODULE_METADATA: list[dict[str, str]] = [
    {
        "code": Module.PERSONS.value,
        "name_vi": "Nhân sự",
        "name_en": "Employees (Persons)",
        "icon": "fa-solid fa-users",
        "badge_color": "#2563eb",
        "desc_vi": "Hồ sơ nhân viên, chức vụ, bộ phận",
        "desc_en": "Employee records, positions, departments",
    },
    {
        "code": Module.SECRETS.value,
        "name_vi": "Mật khẩu nhân viên",
        "name_en": "Employee Secrets",
        "icon": "fa-solid fa-user-shield",
        "badge_color": "#dc2626",
        "desc_vi": "Mật khẩu PC, Email mã hóa AES-256-GCM (Chỉ Admin)",
        "desc_en": "PC & Email credentials with AES-256-GCM encryption",
    },
    {
        "code": Module.ASSETS.value,
        "name_vi": "Tài sản IT",
        "name_en": "IT Assets",
        "icon": "fa-solid fa-laptop",
        "badge_color": "#0284c7",
        "desc_vi": "Máy tính, thiết bị ngoại vi, thông số kỹ thuật",
        "desc_en": "Computers, peripherals, hardware specs",
    },
    {
        "code": Module.ASSIGNMENTS.value,
        "name_vi": "Cấp phát máy",
        "name_en": "Device Assignments",
        "icon": "fa-solid fa-handshake",
        "badge_color": "#0d9488",
        "desc_vi": "Lịch sử bàn giao và thu hồi thiết bị cho nhân sự",
        "desc_en": "Asset assignments & return history",
    },
    {
        "code": Module.LICENSES.value,
        "name_vi": "Bản quyền phần mềm",
        "name_en": "Software Licenses",
        "icon": "fa-solid fa-certificate",
        "badge_color": "#7c3aed",
        "desc_vi": "Kho License key, hạn dùng, phân bổ",
        "desc_en": "License keys, expirations, assignments",
    },
    {
        "code": Module.CARDS.value,
        "name_vi": "Thẻ ra vào",
        "name_en": "Access Cards",
        "icon": "fa-solid fa-id-card",
        "badge_color": "#ea580c",
        "desc_vi": "Thẻ từ vật lý, phân quyền khu vực, sổ mượn trả",
        "desc_en": "Physical keycards, zone access, loan ledger",
    },
    {
        "code": Module.CONTRACTS.value,
        "name_vi": "Hợp đồng mua sắm",
        "name_en": "Procurement Contracts",
        "icon": "fa-solid fa-file-contract",
        "badge_color": "#475569",
        "desc_vi": "Hợp đồng IT, phụ lục chi tiết, tiến độ giao hàng",
        "desc_en": "IT purchase contracts, lines, deliveries",
    },
    {
        "code": Module.PHONES.value,
        "name_vi": "Danh bạ thoại",
        "name_en": "Phone Directory",
        "icon": "fa-solid fa-phone",
        "badge_color": "#16a34a",
        "desc_vi": "Số máy nhánh nội bộ, vị trí điện thoại bàn",
        "desc_en": "Internal extension lines, desk phone locations",
    },
    {
        "code": Module.TRASH.value,
        "name_vi": "Thùng rác",
        "name_en": "Recycle Bin",
        "icon": "fa-solid fa-trash-can",
        "badge_color": "#b91c1c",
        "desc_vi": "Xem và phục hồi các bản ghi đã xóa mềm",
        "desc_en": "View and restore soft-deleted records",
    },
    {
        "code": Module.USERS.value,
        "name_vi": "Tài khoản hệ thống",
        "name_en": "System Users",
        "icon": "fa-solid fa-user-gear",
        "badge_color": "#4338ca",
        "desc_vi": "Tài khoản đăng nhập, trạng thái hoạt động",
        "desc_en": "Portal user accounts, active status",
    },
]

ACTION_METADATA: list[dict[str, str]] = [
    {
        "code": PermissionAction.VIEW.value,
        "name_vi": "Xem",
        "name_en": "View",
        "icon": "fa-solid fa-eye",
        "badge_class": "bg-info-subtle text-info border border-info-subtle",
    },
    {
        "code": PermissionAction.ADD.value,
        "name_vi": "Thêm",
        "name_en": "Add",
        "icon": "fa-solid fa-plus",
        "badge_class": "bg-success-subtle text-success border border-success-subtle",
    },
    {
        "code": PermissionAction.CHANGE.value,
        "name_vi": "Sửa",
        "name_en": "Edit",
        "icon": "fa-solid fa-pen-to-square",
        "badge_class": "bg-primary-subtle text-primary border border-primary-subtle",
    },
    {
        "code": PermissionAction.DELETE.value,
        "name_vi": "Xóa",
        "name_en": "Delete",
        "icon": "fa-solid fa-trash-can",
        "badge_class": "bg-danger-subtle text-danger border border-danger-subtle",
    },
]


def get_role_permission_matrix(db: Session) -> dict[str, Any]:
    """Lấy toàn bộ dữ liệu phục vụ ma trận phân quyền vai trò trực quan."""
    from app.enums import DEFAULT_ROLE_PERMISSIONS
    from app.models import Role

    roles = db.scalars(
        select(Role).where(Role.is_deleted.is_(False)).order_by(Role.id)
    ).all()

    current_permissions: dict[int, dict[str, list[str]]] = {}
    for role in roles:
        current_permissions[role.id] = {}
        perms = db.scalars(
            select(RolePermission).where(RolePermission.role_id == role.id)
        ).all()
        for p in perms:
            if p.module not in current_permissions[role.id]:
                current_permissions[role.id][p.module] = []
            current_permissions[role.id][p.module].append(p.action)

    default_permissions: dict[str, dict[str, list[str]]] = {}
    for role_code, pmap in DEFAULT_ROLE_PERMISSIONS.items():
        code_str = role_code.value if hasattr(role_code, "value") else str(role_code)
        default_permissions[code_str] = {}
        for mod, acts in pmap.items():
            mod_str = mod.value if hasattr(mod, "value") else str(mod)
            default_permissions[code_str][mod_str] = [
                a.value if hasattr(a, "value") else str(a) for a in acts
            ]

    roles_data = [
        {
            "id": r.id,
            "code": r.code,
            "name_en": r.name_en,
            "name_ja": r.name_ja or "",
            "label": f"{r.name_en} ({r.code})",
        }
        for r in roles
    ]

    return {
        "roles": roles_data,
        "modules": MODULE_METADATA,
        "actions": ACTION_METADATA,
        "current_permissions": current_permissions,
        "default_permissions": default_permissions,
    }


def save_role_permissions_matrix(
    db: Session,
    role_id: int,
    new_perms: list[dict[str, str]],
    user_id: int | None = None,
    ip_address: str | None = None,
) -> dict[str, Any]:
    """Cập nhật toàn bộ quyền cho một vai trò từ ma trận quyền, ghi nhận Audit Log."""
    from app.core.audit import record_audit
    from app.enums import AuditAction
    from app.models import Role

    role = db.get(Role, role_id)
    if not role or role.is_deleted:
        raise ValueError(f"Không tìm thấy vai trò ID={role_id}")

    # Lấy quyền hiện hành
    existing_records = db.scalars(
        select(RolePermission).where(RolePermission.role_id == role_id)
    ).all()
    old_set = {(r.module, r.action) for r in existing_records}

    # Chuẩn hóa quyền mới
    valid_modules = {m.value for m in Module}
    valid_actions = {a.value for a in PermissionAction}

    new_set: set[tuple[str, str]] = set()
    for item in new_perms:
        m = item.get("module")
        a = item.get("action")
        if m in valid_modules and a in valid_actions:
            new_set.add((m, a))

    # Chống tự khóa tài khoản Admin (Admin Lockout Protection)
    if role.code == RoleCode.ADMIN.value:
        essential_admin = {
            (Module.USERS.value, PermissionAction.VIEW.value),
            (Module.USERS.value, PermissionAction.ADD.value),
            (Module.USERS.value, PermissionAction.CHANGE.value),
            (Module.AUDIT_LOGS.value, PermissionAction.VIEW.value),
            (Module.SECRETS.value, PermissionAction.VIEW.value),
            (Module.TRASH.value, PermissionAction.VIEW.value),
        }
        if not essential_admin.issubset(new_set):
            raise ValueError("Không thể tước bỏ các quyền quản trị hệ thống cốt lõi (Users, Audit Logs, Secrets, Trash) của vai trò ADMIN.")

    # Xóa quyền bị bỏ
    to_delete = old_set - new_set
    for m, a in to_delete:
        rec = next((r for r in existing_records if r.module == m and r.action == a), None)
        if rec:
            db.delete(rec)

    # Thêm quyền mới
    to_add = new_set - old_set
    for m, a in to_add:
        db.add(RolePermission(role_id=role_id, module=m, action=a))

    record_audit(
        db=db,
        action=AuditAction.UPDATE,
        table_name="role_permissions",
        record_id=role_id,
        user_id=user_id,
        ip_address=ip_address,
        before={"permissions": [f"{m}:{a}" for m, a in sorted(old_set)]},
        after={"permissions": [f"{m}:{a}" for m, a in sorted(new_set)]},
        extra={
            "role_code": role.code,
            "role_name": role.name_en,
            "added_count": len(to_add),
            "removed_count": len(to_delete),
            "total_count": len(new_set),
        },
    )
    db.commit()

    return {
        "success": True,
        "role_id": role_id,
        "role_code": role.code,
        "added": len(to_add),
        "removed": len(to_delete),
        "total": len(new_set),
        "message": f"Đã lưu thành công ma trận quyền cho vai trò {role.name_en} ({len(new_set)} quyền).",
    }


def reset_role_permissions_matrix(
    db: Session,
    role_id: int,
    user_id: int | None = None,
    ip_address: str | None = None,
) -> dict[str, Any]:
    """Khôi phục quyền mặc định cho vai trò theo DEFAULT_ROLE_PERMISSIONS (GEMINI.md)."""
    from app.enums import DEFAULT_ROLE_PERMISSIONS, RoleCode
    from app.models import Role

    role = db.get(Role, role_id)
    if not role or role.is_deleted:
        raise ValueError(f"Không tìm thấy vai trò ID={role_id}")

    try:
        rcode = RoleCode(role.code)
    except ValueError:
        raise ValueError(f"Vai trò {role.code} không có thiết lập mặc định trong DEFAULT_ROLE_PERMISSIONS.")

    default_map = DEFAULT_ROLE_PERMISSIONS.get(rcode, {})
    new_perms_list = []
    for mod, acts in default_map.items():
        for act in acts:
            new_perms_list.append({"module": mod.value, "action": act.value})

    res = save_role_permissions_matrix(
        db=db,
        role_id=role_id,
        new_perms=new_perms_list,
        user_id=user_id,
        ip_address=ip_address,
    )
    res["message"] = f"Đã khôi phục ma trận quyền mặc định cho vai trò {role.name_en}."
    return res

