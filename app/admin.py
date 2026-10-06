"""Tích hợp SQLAdmin cho hệ thống quản trị ITAM - Tokuyama Vietnam.

Quy định bảo mật GEMINI.md:
- Chỉ tài khoản có vai trò ADMIN mới được truy cập /admin.
- Tuyệt đối không để lộ các trường nhạy cảm trong REDACTED_FIELDS (pc_password_enc, email_password_enc, license_key_enc, password_hash).
- AuditLog là bảng bất biến: cấm tạo, sửa, xoá trên giao diện (can_create=False, can_edit=False, can_delete=False).
"""

from __future__ import annotations

from typing import Any
from sqladmin import Admin, ModelView
from sqladmin.authentication import AuthenticationBackend
from starlette.requests import Request
from sqlalchemy import select

from app.core.audit import audit_login, record_audit
from app.core.security import create_session_token, verify_password, verify_session_token
from app.db import SessionLocal
from app.enums import AuditAction, RoleCode
from app.models import (
    AccessCard,
    Asset,
    AssetCategory,
    AssetTag,
    Assignment,
    AuditLog,
    CardLoan,
    Contract,
    ContractLine,
    Department,
    License,
    LicenseAssignment,
    LicenseProduct,
    Location,
    Person,
    PersonSecret,
    Phone,
    Role,
    RolePermission,
    User,
    UserPermissionOverride,
)

COMMON_EXCLUDED_COLUMNS = [
    "created_at", "created_by", "updated_at", "updated_by",
    "is_deleted", "deleted_at", "deleted_by", "delete_reason"
]


class AdminAuth(AuthenticationBackend):
    async def login(self, request: Request) -> bool:
        form = await request.form()
        username = str(form.get("username", "")).strip()
        password = str(form.get("password", "")).strip()
        client_ip = request.client.host if request.client else None

        with SessionLocal() as db:
            user = db.scalar(
                select(User).where(
                    User.username == username,
                    User.is_active.is_(True),
                    User.is_deleted.is_(False),
                )
            )
            if user and user.role and user.role.code == RoleCode.ADMIN.value:
                if verify_password(password, user.password_hash):
                    audit_login(db, user_id=user.id, success=True, username=username, ip_address=client_ip)
                    db.commit()
                    token = create_session_token({
                        "user_id": user.id,
                        "role": user.role.code,
                        "username": user.username,
                    })
                    request.session.update({
                        "token": token,
                        "user_id": user.id,
                        "role": user.role.code,
                        "username": user.username,
                    })
                    return True

            audit_login(db, user_id=user.id if user else None, success=False, username=username, ip_address=client_ip)
            db.commit()

        return False

    async def logout(self, request: Request) -> bool:
        request.session.clear()
        return True

    async def authenticate(self, request: Request) -> bool:
        token = request.session.get("token") or request.cookies.get("itam_session")
        if not token:
            return False

        payload = verify_session_token(token)
        if not payload or payload.get("role") != RoleCode.ADMIN.value:
            return False

        user_id = payload.get("user_id")
        with SessionLocal() as db:
            user = db.scalar(
                select(User).where(
                    User.id == user_id,
                    User.is_active.is_(True),
                    User.is_deleted.is_(False),
                )
            )
            if not user or not user.role or user.role.code != RoleCode.ADMIN.value:
                return False

        request.session["user_id"] = user_id
        request.session["role"] = RoleCode.ADMIN.value
        return True


authentication_backend = AdminAuth(secret_key="tokuyama-sqladmin-auth-secret-key-2026")


# --- Base Model View ---

class BaseAdminView(ModelView):
    can_export = True
    page_size = 25
    page_size_options = [10, 25, 50, 100]
    form_excluded_columns = COMMON_EXCLUDED_COLUMNS

    async def after_model_change(self, data: dict, model: Any, is_created: bool, request: Request) -> None:
        action = AuditAction.CREATE if is_created else AuditAction.UPDATE
        user_id = request.session.get("user_id")
        record_id = getattr(model, "id", None)
        table_name = getattr(self.model, "__tablename__", "unknown")
        client_ip = request.client.host if request.client else None

        try:
            with SessionLocal() as db:
                record_audit(
                    db=db,
                    action=action,
                    table_name=table_name,
                    record_id=record_id,
                    user_id=user_id,
                    after=data,
                    ip_address=client_ip,
                )
                db.commit()
        except Exception:
            pass


# --- Model Views ---

class UserAdmin(BaseAdminView, model=User):
    name = "Người dùng"
    name_plural = "Tài khoản Đăng nhập"
    icon = "fa-solid fa-users-gear"
    category = "Hệ thống & Phân quyền"
    column_list = [User.id, User.username, User.display_name, User.role, User.preferred_lang, User.is_active, User.last_login_at]
    column_searchable_list = [User.username, User.display_name]
    form_excluded_columns = COMMON_EXCLUDED_COLUMNS + ["password_hash"]


class RoleAdmin(BaseAdminView, model=Role):
    name = "Vai trò"
    name_plural = "Vai trò Hệ thống"
    icon = "fa-solid fa-user-shield"
    category = "Hệ thống & Phân quyền"
    column_list = [Role.id, Role.code, Role.name_en, Role.name_ja]


class RolePermissionAdmin(BaseAdminView, model=RolePermission):
    name = "Quyền vai trò"
    name_plural = "Ma trận Quyền Vai trò"
    icon = "fa-solid fa-key"
    category = "Hệ thống & Phân quyền"
    column_list = [RolePermission.id, RolePermission.role, RolePermission.module, RolePermission.action]


class UserPermissionOverrideAdmin(BaseAdminView, model=UserPermissionOverride):
    name = "Ghi đè quyền"
    name_plural = "Quyền riêng Người dùng"
    icon = "fa-solid fa-user-pen"
    category = "Hệ thống & Phân quyền"
    column_list = [UserPermissionOverride.id, UserPermissionOverride.user_id, UserPermissionOverride.module, UserPermissionOverride.action, UserPermissionOverride.granted]


class DepartmentAdmin(BaseAdminView, model=Department):
    name = "Phòng ban"
    name_plural = "Danh mục Phòng ban"
    icon = "fa-solid fa-sitemap"
    category = "Danh mục Dùng chung"
    column_list = [Department.id, Department.code, Department.name_en, Department.name_ja]


class AssetCategoryAdmin(BaseAdminView, model=AssetCategory):
    name = "Loại tài sản"
    name_plural = "Danh mục Loại tài sản"
    icon = "fa-solid fa-tags"
    category = "Danh mục Dùng chung"
    column_list = [AssetCategory.id, AssetCategory.name_en, AssetCategory.name_ja]


class AssetTagAdmin(BaseAdminView, model=AssetTag):
    name = "Nhãn tài sản"
    name_plural = "Danh mục Nhãn (Tags)"
    icon = "fa-solid fa-tag"
    category = "Danh mục Dùng chung"
    column_list = [AssetTag.id, AssetTag.code, AssetTag.name_en, AssetTag.color]


class LocationAdmin(BaseAdminView, model=Location):
    name = "Vị trí / Phòng"
    name_plural = "Danh mục Vị trí"
    icon = "fa-solid fa-location-dot"
    category = "Danh mục Dùng chung"
    column_list = [Location.id, Location.building, Location.floor, Location.room_en, Location.room_ja, Location.is_access_controlled]


class PersonAdmin(BaseAdminView, model=Person):
    name = "Nhân sự"
    name_plural = "Hồ sơ Nhân sự"
    icon = "fa-solid fa-id-card-clip"
    category = "Nhân sự"
    column_list = [Person.id, Person.staff_code, Person.full_name, Person.department, Person.status, Person.email, Person.start_working_date]
    column_searchable_list = [Person.staff_code, Person.full_name, Person.email]
    form_excluded_columns = COMMON_EXCLUDED_COLUMNS + ["secret"]


class PersonSecretAdmin(BaseAdminView, model=PersonSecret):
    name = "Mật khẩu nhân viên"
    name_plural = "Kho Mật khẩu Nhân sự"
    icon = "fa-solid fa-user-lock"
    category = "Nhân sự"
    can_create = False
    can_edit = False
    can_delete = False
    column_list = [PersonSecret.person_id]


class AssetAdmin(BaseAdminView, model=Asset):
    name = "Tài sản IT"
    name_plural = "Danh sách Thiết bị"
    icon = "fa-solid fa-laptop"
    category = "Tài sản"
    column_list = [Asset.id, Asset.asset_code, Asset.vendor_code, Asset.serial, Asset.category, Asset.status, Asset.model]
    column_searchable_list = [Asset.asset_code, Asset.serial, Asset.vendor_code, Asset.model]


class AssignmentAdmin(BaseAdminView, model=Assignment):
    name = "Bàn giao thiết bị"
    name_plural = "Lịch sử Cấp phát Tài sản"
    icon = "fa-solid fa-handshake"
    category = "Tài sản"
    column_list = [Assignment.id, Assignment.asset, Assignment.person, Assignment.borrowed_at, Assignment.returned_at]


class LicenseProductAdmin(BaseAdminView, model=LicenseProduct):
    name = "Sản phẩm License"
    name_plural = "Danh mục Phần mềm"
    icon = "fa-solid fa-compact-disc"
    category = "License"
    column_list = [LicenseProduct.id, LicenseProduct.name, LicenseProduct.vendor]


class LicenseAdmin(BaseAdminView, model=License):
    name = "Bản quyền License"
    name_plural = "Kho License Phần mềm"
    icon = "fa-solid fa-certificate"
    category = "License"
    column_list = [License.id, License.product, License.seats, License.start_date, License.expiry_date]
    form_excluded_columns = COMMON_EXCLUDED_COLUMNS + ["license_key_enc"]


class LicenseAssignmentAdmin(BaseAdminView, model=LicenseAssignment):
    name = "Gán License"
    name_plural = "Phân bổ Bản quyền"
    icon = "fa-solid fa-user-check"
    category = "License"
    column_list = [LicenseAssignment.id, LicenseAssignment.license, LicenseAssignment.person_id, LicenseAssignment.asset_id, LicenseAssignment.assigned_at, LicenseAssignment.removed_at]


class AccessCardAdmin(BaseAdminView, model=AccessCard):
    name = "Thẻ ra vào"
    name_plural = "Danh sách Thẻ từ"
    icon = "fa-solid fa-address-card"
    category = "Thẻ ra vào"
    column_list = [AccessCard.id, AccessCard.card_no, AccessCard.card_type, AccessCard.status]


class CardLoanAdmin(BaseAdminView, model=CardLoan):
    name = "Mượn thẻ từ"
    name_plural = "Sổ Mượn-Trả Thẻ"
    icon = "fa-solid fa-clock-rotate-left"
    category = "Thẻ ra vào"
    column_list = [CardLoan.id, CardLoan.card, CardLoan.person_id, CardLoan.external_name, CardLoan.borrowed_at, CardLoan.returned_at]


class ContractAdmin(BaseAdminView, model=Contract):
    name = "Hợp đồng"
    name_plural = "Hợp đồng Mua sắm IT"
    icon = "fa-solid fa-file-contract"
    category = "Hợp đồng"
    column_list = [Contract.id, Contract.code, Contract.vendor_name, Contract.signed_date, Contract.delivery_status]


class ContractLineAdmin(BaseAdminView, model=ContractLine):
    name = "Hạng mục Hợp đồng"
    name_plural = "Chi tiết Hạng mục"
    icon = "fa-solid fa-list-check"
    category = "Hợp đồng"
    column_list = [ContractLine.id, ContractLine.contract, ContractLine.item_type, ContractLine.qty_ordered]


class PhoneAdmin(BaseAdminView, model=Phone):
    name = "Thiết bị Thoại"
    name_plural = "Danh bạ & Thiết bị Điện thoại"
    icon = "fa-solid fa-phone"
    category = "Danh bạ thoại"
    column_list = [Phone.id, Phone.extension_number, Phone.device_name, Phone.device_type, Phone.location, Phone.is_active]


class AuditLogAdmin(BaseAdminView, model=AuditLog):
    name = "Nhật ký kiểm toán"
    name_plural = "Audit Trail (Bất biến)"
    icon = "fa-solid fa-shield-halved"
    category = "Truy vết"
    can_create = False
    can_edit = False
    can_delete = False
    column_list = [AuditLog.id, AuditLog.created_at, AuditLog.user_id, AuditLog.action, AuditLog.table_name, AuditLog.record_id, AuditLog.ip_address]
    column_searchable_list = [AuditLog.table_name, AuditLog.action]


def setup_admin(app, engine):
    admin = Admin(
        app,
        engine,
        title="Tokuyama IT Portal",
        logo_url="/static/img/logo.png",
        authentication_backend=authentication_backend,
        base_url="/admin",
    )

    # 1. Hệ thống & phân quyền
    admin.add_view(UserAdmin)
    admin.add_view(RoleAdmin)
    admin.add_view(RolePermissionAdmin)
    admin.add_view(UserPermissionOverrideAdmin)

    # 2. Danh mục dùng chung
    admin.add_view(DepartmentAdmin)
    admin.add_view(AssetCategoryAdmin)
    admin.add_view(AssetTagAdmin)
    admin.add_view(LocationAdmin)

    # 3. Nhân sự
    admin.add_view(PersonAdmin)
    admin.add_view(PersonSecretAdmin)

    # 4. Tài sản
    admin.add_view(AssetAdmin)
    admin.add_view(AssignmentAdmin)

    # 5. License
    admin.add_view(LicenseProductAdmin)
    admin.add_view(LicenseAdmin)
    admin.add_view(LicenseAssignmentAdmin)

    # 6. Thẻ ra vào
    admin.add_view(AccessCardAdmin)
    admin.add_view(CardLoanAdmin)

    # 7. Hợp đồng
    admin.add_view(ContractAdmin)
    admin.add_view(ContractLineAdmin)

    # 8. Danh bạ thoại
    admin.add_view(PhoneAdmin)

    # 9. Truy vết
    admin.add_view(AuditLogAdmin)

    return admin
