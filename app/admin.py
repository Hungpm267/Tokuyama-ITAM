"""Tích hợp SQLAdmin cho hệ thống quản trị ITAM - Tokuyama Vietnam.

Quy định bảo mật GEMINI.md:
- Chỉ tài khoản có vai trò ADMIN mới được truy cập /admin.
- Tuyệt đối không để lộ các trường nhạy cảm trong REDACTED_FIELDS (pc_password_enc, email_password_enc, license_key_enc, password_hash).
- AuditLog là bảng bất biến: cấm tạo, sửa, xoá trên giao diện (can_create=False, can_edit=False, can_delete=False).
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any
from sqladmin import Admin, ModelView
from sqladmin.authentication import AuthenticationBackend, login_required
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response
from sqlalchemy import Select, func, select

from app.core.audit import audit_login, record_audit
from app.core.security import (
    SESSION_SECRET,
    create_session_token,
    hash_password,
    verify_password,
    verify_session_token,
)
from wtforms import Form, PasswordField, SelectField
from wtforms.widgets import PasswordInput
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
    def __init__(self, secret_key: str) -> None:
        super().__init__(secret_key=secret_key)
        from starlette.middleware import Middleware
        from starlette.middleware.sessions import SessionMiddleware

        self.middlewares = [
            Middleware(
                SessionMiddleware,
                secret_key=secret_key,
                session_cookie="admin_session",
            )
        ]

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
            if user:
                if user.role and user.role.code == RoleCode.ADMIN.value:
                    if verify_password(password, user.password_hash):
                        audit_login(db, user_id=user.id, success=True, username=username, ip_address=client_ip)
                        db.commit()
                        token = create_session_token({
                            "user_id": user.id,
                            "role": user.role.code,
                            "username": user.username,
                        })
                        lang = user.preferred_lang or request.cookies.get("itam_lang") or "vi"
                        request.session.update({
                            "token": token,
                            "user_id": user.id,
                            "role": user.role.code,
                            "username": user.username,
                            "lang": lang,
                        })
                        return True
                    else:
                        request.state.login_error = "Mật khẩu không chính xác."
                else:
                    role_title = user.role.name_ja or user.role.name_en if user.role else "chưa phân quyền"
                    request.state.login_error = f"Tài khoản '{username}' có vai trò {role_title}, không có quyền truy cập cổng Quản trị (yêu cầu vai trò ADMIN)."
            else:
                request.state.login_error = "Tên đăng nhập không tồn tại hoặc đã bị khóa."

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

            if "lang" not in request.session:
                request.session["lang"] = user.preferred_lang or request.cookies.get("itam_lang") or "vi"

        request.session["user_id"] = user_id
        request.session["role"] = RoleCode.ADMIN.value
        return True


authentication_backend = AdminAuth(secret_key=SESSION_SECRET)


def humanize_error_str(msg: str, lang: str = "vi") -> str:
    """Chuyển đổi các thông báo lỗi kỹ thuật/SQL/Constraint thành thông báo tiếng Việt/Anh thân thiện."""
    if not msg:
        return ""
    m = str(msg)
    is_en = (lang == "en")

    if "expiry_after_start" in m:
        return "Expiry date cannot be before start date." if is_en else "Ngày hết hạn không được trước ngày bắt đầu."
    if "returned_after_borrowed" in m:
        return "Return date cannot be before borrow date." if is_en else "Ngày trả không được trước ngày mượn."
    if "removed_after_assigned" in m:
        return "Removal date cannot be before assignment date." if is_en else "Ngày thu hồi bản quyền không được trước ngày cấp phát."
    if "seats_positive" in m:
        return "Seats count must be greater than 0." if is_en else "Số lượng bản quyền (Seats) phải lớn hơn 0."
    if "qty_positive" in m:
        return "Ordered quantity must be greater than 0." if is_en else "Số lượng đặt hàng phải lớn hơn 0."
    if "has_some_identifier" in m:
        return "Asset must have at least one identifier (GA code, Vendor code or Serial)." if is_en else "Tài sản phải có ít nhất một mã định danh (Mã GA, Mã Vendor hoặc Số Serial)."
    if "target_required" in m:
        return "License must be assigned to either an asset or a person." if is_en else "Bản quyền phải được gán cho thiết bị hoặc nhân viên."
    if "borrower_required" in m:
        return "Must select a person or enter external borrower name." if is_en else "Mượn thẻ phải chọn nhân viên hoặc nhập tên người mượn ngoài."
    if "staff_code_format" in m:
        return "Staff code does not match standard TVC format (e.g. TVC00001)." if is_en else "Mã nhân viên không đúng định dạng chuẩn TVC (Ví dụ: TVC00001)."
    if "smallint out of range" in m or "numericvalueoutofrange" in m.lower():
        return "Numeric value is out of allowable range." if is_en else "Giá trị số nhập vào vượt quá giới hạn cho phép."

    if "unique constraint" in m.lower() or "uniqueviolation" in m.lower():
        if "serial" in m:
            return "Serial number already exists in system." if is_en else "Số Serial này đã tồn tại trong hệ thống (bị trùng lặp)."
        if "asset_code" in m:
            return "Asset code already exists in system." if is_en else "Mã tài sản này đã tồn tại trong hệ thống (bị trùng lặp)."
        if "vendor_code" in m:
            return "Vendor code already exists in system." if is_en else "Mã Vendor này đã tồn tại trong hệ thống (bị trùng lặp)."
        if "card_no" in m:
            return "Card number already exists in system." if is_en else "Số thẻ này đã tồn tại trong hệ thống (bị trùng lặp)."
        if "staff_code" in m:
            return "Staff code already exists in system." if is_en else "Mã nhân viên này đã tồn tại trong hệ thống (bị trùng lặp)."
        if "username" in m:
            return "Username already exists in system." if is_en else "Tên đăng nhập này đã tồn tại trong hệ thống (bị trùng lặp)."
        return "Record already exists in system (duplicate)." if is_en else "Dữ liệu bị trùng lặp với bản ghi đã tồn tại trong hệ thống."

    if "foreign key" in m.lower() or "foreignkeyviolation" in m.lower():
        return "Cannot save or delete because data is referenced elsewhere." if is_en else "Không thể lưu hoặc xóa vì dữ liệu đang được liên kết với bản ghi khác."
    if "not-null constraint" in m.lower() or "notnullviolation" in m.lower():
        return "Please fill in all required fields." if is_en else "Vui lòng nhập đầy đủ các trường thông tin bắt buộc."

    if "(psycopg." in m or "[SQL:" in m:
        clean = m.split("[SQL:")[0].strip()
        clean = clean.split("DETAIL:")[0].strip()
        return clean

    return m


# --- Base Model View ---

class BaseAdminView(ModelView):
    can_export = True
    page_size = 25
    page_size_options = [10, 25, 50, 100]
    form_excluded_columns = COMMON_EXCLUDED_COLUMNS

    async def insert_model(self, request: Request, data: dict) -> Any:
        try:
            return await super().insert_model(request, data)
        except Exception as e:
            lang = request.session.get("lang", "vi")
            raise ValueError(humanize_error_str(str(e), lang=lang)) from e

    async def update_model(self, request: Request, pk: Any, data: dict) -> Any:
        try:
            return await super().update_model(request, pk, data)
        except Exception as e:
            lang = request.session.get("lang", "vi")
            raise ValueError(humanize_error_str(str(e), lang=lang)) from e

    async def on_model_change(
        self, data: dict, model: Any, is_created: bool, request: Request
    ) -> None:
        lang = request.session.get("lang", "vi")
        is_en = (lang == "en")

        # Kiểm tra tính hợp lệ của ngày tháng trước khi ghi DB
        if "start_date" in data and "expiry_date" in data:
            s = data.get("start_date")
            ex = data.get("expiry_date")
            if s and ex and ex < s:
                msg = "Expiry date cannot be before start date." if is_en else "Ngày hết hạn không được trước ngày bắt đầu."
                raise ValueError(msg)

        if "borrowed_at" in data and "returned_at" in data:
            b = data.get("borrowed_at")
            r = data.get("returned_at")
            if b and r and r < b:
                msg = "Return date cannot be before borrow date." if is_en else "Ngày trả không được trước ngày mượn."
                raise ValueError(msg)

        if "assigned_at" in data and "removed_at" in data:
            a = data.get("assigned_at")
            rem = data.get("removed_at")
            if a and rem and rem < a:
                msg = "Removal date cannot be before assignment date." if is_en else "Ngày thu hồi bản quyền không được trước ngày cấp phát."
                raise ValueError(msg)

        await super().on_model_change(data, model, is_created, request)


    def list_query(self, request: Request) -> Select:
        stmt = super().list_query(request)
        if hasattr(self.model, "is_deleted"):
            stmt = stmt.where(self.model.is_deleted.is_(False))
        return stmt

    def count_query(self, request: Request) -> Select:
        stmt = super().count_query(request)
        if hasattr(self.model, "is_deleted"):
            stmt = stmt.where(self.model.is_deleted.is_(False))
        return stmt

    def form_edit_query(self, request: Request) -> Select:
        stmt = super().form_edit_query(request)
        if hasattr(self.model, "is_deleted"):
            stmt = stmt.where(self.model.is_deleted.is_(False))
        return stmt

    async def get_object_for_delete(self, value: Any) -> Any:
        stmt = self._stmt_by_identifier(value)
        if hasattr(self.model, "is_deleted"):
            stmt = stmt.where(self.model.is_deleted.is_(False))
        return await self._get_object_by_pk(stmt)

    async def delete_model(self, request: Request, pk: Any) -> None:
        user_id = request.session.get("user_id")
        current_user_id = int(user_id) if user_id is not None else None

        # Chặn tự xóa tài khoản của chính mình đang đăng nhập
        if self.model is User and current_user_id is not None and str(pk) == str(current_user_id):
            raise HTTPException(
                status_code=400,
                detail="Không thể xóa tài khoản của chính bạn đang đăng nhập.",
            )

        with SessionLocal() as db:
            stmt = self._stmt_by_identifier(str(pk))
            obj = db.scalar(stmt)
            if not obj:
                return

            # Chặn xóa vai trò ADMIN hệ thống
            if self.model is Role and getattr(obj, "code", None) == RoleCode.ADMIN.value:
                raise HTTPException(
                    status_code=400,
                    detail="Không thể xóa vai trò ADMIN hệ thống.",
                )

            table_name = getattr(self.model, "__tablename__", "unknown")
            client_ip = request.client.host if request.client else None

            # Lưu snapshot trước khi xóa để đưa vào audit log
            before_data: dict[str, Any] = {}
            if hasattr(self.model, "__table__"):
                for col in self.model.__table__.columns:
                    val = getattr(obj, col.name, None)
                    if isinstance(val, (dt.datetime, dt.date)):
                        val = val.isoformat()
                    before_data[col.name] = val

            delete_reason = request.query_params.get("delete_reason") or "Xóa từ giao diện quản trị ITAM"

            if hasattr(self.model, "is_deleted"):
                # Xóa mềm tuân thủ GEMINI.md Quy tắc 6 (bắt buộc deleted_at và delete_reason)
                obj.is_deleted = True
                obj.deleted_at = dt.datetime.now(dt.timezone.utc)
                obj.deleted_by = current_user_id
                obj.delete_reason = delete_reason

                record_audit(
                    db=db,
                    action=AuditAction.DELETE,
                    table_name=table_name,
                    record_id=getattr(obj, "id", None),
                    user_id=current_user_id,
                    before=before_data,
                    ip_address=client_ip,
                )
                db.commit()
            else:
                db.delete(obj)
                record_audit(
                    db=db,
                    action=AuditAction.DELETE,
                    table_name=table_name,
                    record_id=getattr(obj, "id", None),
                    user_id=current_user_id,
                    before=before_data,
                    ip_address=client_ip,
                )
                db.commit()

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
    form_excluded_columns = COMMON_EXCLUDED_COLUMNS + ["password_hash", "last_login_at"]
    form_overrides = {
        "preferred_lang": SelectField,
    }
    form_args = {
        "preferred_lang": {
            "choices": [("vi", "Tiếng Việt (vi)"), ("en", "English (en)")],
            "default": "vi",
        }
    }

    async def scaffold_form(self, rules: list[str] | None = None) -> type[Form]:
        base_form = await super().scaffold_form(rules)

        class UserFormWithPassword(base_form):
            password = PasswordField(
                "Mật khẩu",
                widget=PasswordInput(hide_value=True),
                render_kw={
                    "placeholder": "Nhập mật khẩu (để trống nếu không đổi)",
                    "class": "form-control",
                    "autocomplete": "new-password",
                },
            )

        return UserFormWithPassword

    async def on_model_change(
        self, data: dict, model: Any, is_created: bool, request: Request
    ) -> None:
        raw_password = data.pop("password", None)
        if is_created:
            if not raw_password or not str(raw_password).strip():
                raise ValueError("Vui lòng nhập mật khẩu khi tạo người dùng mới.")
            data["password_hash"] = hash_password(str(raw_password).strip())
        else:
            if raw_password and str(raw_password).strip():
                data["password_hash"] = hash_password(str(raw_password).strip())

        await super().on_model_change(data, model, is_created, request)


class RoleAdmin(BaseAdminView, model=Role):
    name = "Vai trò"
    name_plural = "Vai trò Hệ thống"
    icon = "fa-solid fa-user-shield"
    category = "Hệ thống & Phân quyền"
    column_list = [Role.id, Role.code, Role.name_en, Role.name_ja]
    form_columns = [Role.code, Role.name_en, Role.name_ja]


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
    form_excluded_columns = COMMON_EXCLUDED_COLUMNS + ["secret", "assignments"]


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
    form_excluded_columns = COMMON_EXCLUDED_COLUMNS + ["assignments"]


class AssignmentAdmin(BaseAdminView, model=Assignment):
    name = "Bàn giao thiết bị"
    name_plural = "Lịch sử Cấp phát Tài sản"
    icon = "fa-solid fa-handshake"
    category = "Tài sản"
    can_delete = False
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
    form_excluded_columns = COMMON_EXCLUDED_COLUMNS + ["license_key_enc", "key_version", "assignments"]


class LicenseAssignmentAdmin(BaseAdminView, model=LicenseAssignment):
    name = "Gán License"
    name_plural = "Phân bổ Bản quyền"
    icon = "fa-solid fa-user-check"
    category = "License"
    can_delete = False
    column_list = [
        LicenseAssignment.id,
        LicenseAssignment.license,
        LicenseAssignment.asset,
        LicenseAssignment.person,
        LicenseAssignment.assigned_at,
        LicenseAssignment.expiry_date,
        LicenseAssignment.removed_at,
    ]
    form_columns = [
        "license",
        "asset",
        "person",
        "assigned_at",
        "expiry_date",
        "removed_at",
        "note",
    ]


class AccessCardAdmin(BaseAdminView, model=AccessCard):
    name = "Thẻ ra vào"
    name_plural = "Danh sách Thẻ từ"
    icon = "fa-solid fa-address-card"
    category = "Thẻ ra vào"
    column_list = [AccessCard.id, AccessCard.card_no, AccessCard.card_type, AccessCard.status]
    form_excluded_columns = COMMON_EXCLUDED_COLUMNS + ["loans"]


class CardLoanAdmin(BaseAdminView, model=CardLoan):
    name = "Mượn thẻ từ"
    name_plural = "Sổ Mượn-Trả Thẻ"
    icon = "fa-solid fa-clock-rotate-left"
    category = "Thẻ ra vào"
    can_delete = False
    column_list = [CardLoan.id, CardLoan.card, CardLoan.person_id, CardLoan.external_name, CardLoan.borrowed_at, CardLoan.returned_at]


class ContractAdmin(BaseAdminView, model=Contract):
    name = "Hợp đồng"
    name_plural = "Hợp đồng Mua sắm IT"
    icon = "fa-solid fa-file-contract"
    category = "Hợp đồng"
    column_list = [Contract.id, Contract.code, Contract.vendor_name, Contract.signed_date, Contract.delivery_status]
    form_excluded_columns = COMMON_EXCLUDED_COLUMNS + ["lines"]


class ContractLineAdmin(BaseAdminView, model=ContractLine):
    name = "Hạng mục Hợp đồng"
    name_plural = "Chi tiết Hạng mục"
    icon = "fa-solid fa-list-check"
    category = "Hợp đồng"
    column_list = [ContractLine.id, ContractLine.contract, ContractLine.item_type, ContractLine.qty_ordered]
    form_excluded_columns = COMMON_EXCLUDED_COLUMNS + ["assets"]


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


BASE_DIR = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = BASE_DIR / "templates"


class TokuyamaAdmin(Admin):
    async def login(self, request: Request) -> Response:
        assert self.authentication_backend is not None

        context = {}
        if request.method == "GET":
            return await self.templates.TemplateResponse(request, "sqladmin/login.html")

        ok = await self.authentication_backend.login(request)
        if not ok:
            context["error"] = getattr(
                request.state, "login_error", "Tên đăng nhập hoặc mật khẩu không chính xác."
            )
            return await self.templates.TemplateResponse(
                request, "sqladmin/login.html", context, status_code=400
            )

        return RedirectResponse(request.url_for("admin:index"), status_code=302)

    @login_required
    async def index(self, request: Request) -> Response:
        """Dashboard tổng quan hệ thống ITAM Tokuyama theo triết lý Swiss."""
        from app.core.i18n import get_current_lang, translate

        current_lang = get_current_lang(request)
        with SessionLocal() as db:
            asset_count = db.scalar(
                select(func.count()).select_from(Asset).where(Asset.is_deleted.is_(False))
            ) or 0
            assignment_count = db.scalar(
                select(func.count()).select_from(Assignment).where(Assignment.returned_at.is_(None))
            ) or 0
            license_count = db.scalar(
                select(func.count()).select_from(License).where(License.is_deleted.is_(False))
            ) or 0
            card_count = db.scalar(
                select(func.count()).select_from(AccessCard).where(AccessCard.is_deleted.is_(False))
            ) or 0
            person_count = db.scalar(
                select(func.count()).select_from(Person).where(Person.is_deleted.is_(False))
            ) or 0
            contract_count = db.scalar(
                select(func.count()).select_from(Contract).where(Contract.is_deleted.is_(False))
            ) or 0
            active_card_loans = db.scalar(
                select(func.count()).select_from(CardLoan).where(CardLoan.returned_at.is_(None))
            ) or 0
            recent_logs = db.scalars(
                select(AuditLog).order_by(AuditLog.id.desc()).limit(8)
            ).all()

        allocation_rate = int(round((assignment_count / asset_count) * 100)) if asset_count > 0 else 0

        context = {
            "request": request,
            "admin": self,
            "current_lang": current_lang,
            "title": translate("Tổng quan Quản trị", current_lang),
            "subtitle": translate("IT Asset Management System", current_lang),
            "asset_count": asset_count,
            "assignment_count": assignment_count,
            "license_count": license_count,
            "card_count": card_count,
            "person_count": person_count,
            "contract_count": contract_count,
            "active_card_loans": active_card_loans,
            "allocation_rate": allocation_rate,
            "recent_logs": recent_logs,
        }
        return await self.templates.TemplateResponse(request, "sqladmin/index.html", context)


def setup_admin(app, engine):
    admin = TokuyamaAdmin(
        app,
        engine,
        title="Tokuyama IT Portal",
        logo_url="/static/img/logo.svg",
        authentication_backend=authentication_backend,
        base_url="/admin",
        templates_dir=str(TEMPLATES_DIR),
    )

    from app.core.i18n import get_current_lang, translate

    admin.templates.env.globals["t"] = translate
    admin.templates.env.filters["t"] = translate
    admin.templates.env.globals["get_current_lang"] = get_current_lang
    admin.templates.env.globals["humanize_error"] = humanize_error_str
    admin.templates.env.filters["humanize_error"] = humanize_error_str

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
