"""Tập giá trị cố định của hệ thống.

QUY TẮC: mọi trạng thái trong DB đều là ENUM native của PostgreSQL.
KHÔNG dùng VARCHAR tự do cho trạng thái. Thêm giá trị mới = viết migration
`ALTER TYPE ... ADD VALUE`, không sửa trực tiếp.
"""

from enum import Enum


class PersonStatus(str, Enum):
    SCHEDULED = "SCHEDULED"  # sắp vào làm
    ACTIVE = "ACTIVE"  # đang làm
    RESIGNED = "RESIGNED"  # đã nghỉ việc


class PersonType(str, Enum):
    EMPLOYEE = "EMPLOYEE"  # nhân viên chính thức, mã TVC
    VENDOR = "VENDOR"  # vendor thuê tạm thời, mã VND-NNN do app cấp
    BUSINESS_TRIP = "BUSINESS_TRIP"  # người Nhật sang công tác, mã JP-NNN do app cấp


class AssetStatus(str, Enum):
    IN_STOCK = "IN_STOCK"  # trong kho
    IN_USE = "IN_USE"  # đang cho mượn
    REPAIR = "REPAIR"  # đang sửa
    DISPOSED = "DISPOSED"  # đã thanh lý
    LOST = "LOST"  # mất


#: Trạng thái mà tài sản KHÔNG được phép cho mượn.
ASSET_NOT_LOANABLE = frozenset(
    {AssetStatus.IN_USE, AssetStatus.REPAIR, AssetStatus.DISPOSED, AssetStatus.LOST}
)


class AuditAction(str, Enum):
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    RESTORE = "RESTORE"
    LOGIN = "LOGIN"
    LOGIN_FAIL = "LOGIN_FAIL"
    REVEAL = "REVEAL"  # xem mật khẩu


class PermissionAction(str, Enum):
    VIEW = "view"
    ADD = "add"
    CHANGE = "change"
    DELETE = "delete"


class Module(str, Enum):
    """Các module dùng cho phân quyền RBAC."""

    PERSONS = "persons"
    SECRETS = "secrets"  # xem mật khẩu nhân viên - quyền RIÊNG, chỉ Admin
    ASSETS = "assets"
    ASSIGNMENTS = "assignments"
    AUDIT = "audit"
    TRASH = "trash"
    USERS = "users"


class RoleCode(str, Enum):
    ADMIN = "ADMIN"
    GA_MANAGER = "GA_MANAGER"
    EXECUTIVE = "EXECUTIVE"


#: Ma trận quyền mặc định (BRD mục "Phân quyền RBAC").
#: Dùng để seed bảng role_permissions. Sau khi seed, Admin chỉnh qua UI.
DEFAULT_ROLE_PERMISSIONS: dict[RoleCode, dict[Module, list[PermissionAction]]] = {
    RoleCode.ADMIN: {
        m: [
            PermissionAction.VIEW,
            PermissionAction.ADD,
            PermissionAction.CHANGE,
            PermissionAction.DELETE,
        ]
        for m in Module
    },
    # Giai đoạn thu hẹp: chỉ còn hai mức - Admin và chỉ xem.
    RoleCode.GA_MANAGER: {
        Module.PERSONS: [PermissionAction.VIEW],
        Module.ASSETS: [PermissionAction.VIEW],
        Module.ASSIGNMENTS: [PermissionAction.VIEW],
    },
    RoleCode.EXECUTIVE: {
        Module.PERSONS: [PermissionAction.VIEW],
        Module.ASSETS: [PermissionAction.VIEW],
        Module.ASSIGNMENTS: [PermissionAction.VIEW],
        Module.AUDIT: [PermissionAction.VIEW],
    },
}

# Lưu ý: ADMIN ở trên được cấp đủ 4 action trên mọi module, kể cả AUDIT và SECRETS.
# Nhưng audit_logs được trigger DB chặn UPDATE/DELETE, nên quyền change/delete trên
# module AUDIT là vô hiệu ở tầng dữ liệu - đó là chủ ý.
