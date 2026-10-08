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
from sqladmin.helpers import get_object_identifier
from starlette.datastructures import FormData, URL
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response
from sqlalchemy import Select, func, select
from sqlalchemy.orm import selectinload
from markupsafe import Markup


from app.core.audit import audit_login, record_audit
from app.core.i18n import DEFAULT_ADMIN_COLUMN_LABELS
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
from app.enums import AssetStatus, AuditAction, CardStatus, RoleCode
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

            request.session["user_id"] = user.id
            request.session["username"] = user.username
            request.session["display_name"] = user.display_name or user.username
            request.session["role"] = RoleCode.ADMIN.value
        return True


authentication_backend = AdminAuth(secret_key=SESSION_SECRET)


def humanize_error_str(msg: str, lang: str = "vi") -> str:
    """Chuyển đổi các thông báo lỗi kỹ thuật/SQL/Constraint thành thông báo tiếng Việt/Anh/Nhật thân thiện."""
    if not msg:
        return ""
    m = str(msg)
    is_en = (lang == "en")
    is_ja = (lang == "ja")

    def _tr(vi: str, en: str, ja: str) -> str:
        if is_ja:
            return ja
        if is_en:
            return en
        return vi

    if "expiry_after_start" in m:
        return _tr("Ngày hết hạn không được trước ngày bắt đầu.", "Expiry date cannot be before start date.", "有効期限を開始日より前にすることはできません。")
    if "returned_after_borrowed" in m:
        return _tr("Ngày trả không được trước ngày mượn.", "Return date cannot be before borrow date.", "返却日を貸出日より前にすることはできません。")
    if "removed_after_assigned" in m:
        return _tr("Ngày thu hồi bản quyền không được trước ngày cấp phát.", "Removal date cannot be before assignment date.", "ライセンス回収日を割当日より前にすることはできません。")
    if "seats_positive" in m:
        return _tr("Số lượng bản quyền (Seats) phải lớn hơn 0.", "Seats count must be greater than 0.", "ライセンス数（Seats）は1以上である必要があります。")
    if "qty_positive" in m:
        return _tr("Số lượng đặt hàng phải lớn hơn 0.", "Ordered quantity must be greater than 0.", "発注数量は1以上である必要があります。")
    if "has_some_identifier" in m:
        return _tr("Tài sản phải có ít nhất một mã định danh (Mã GA, Mã Vendor hoặc Số Serial).", "Asset must have at least one identifier (GA code, Vendor code or Serial).", "資産には少なくとも1つの識別子（GAコード、ベンダーコード、またはシリアル）が必要です。")
    if "target_required" in m:
        return _tr("Bản quyền phải được gán cho thiết bị hoặc nhân viên.", "License must be assigned to either an asset or a person.", "ライセンスは機器または担当者のいずれかに割り当てる必要があります。")
    if "borrower_required" in m:
        return _tr("Mượn thẻ phải chọn nhân viên hoặc nhập tên người mượn ngoài.", "Must select a person or enter external borrower name.", "担当者を選択するか、外部借用者名を入力してください。")
    if "staff_code_format" in m:
        return _tr("Mã nhân viên không đúng định dạng chuẩn TVC (Ví dụ: TVC00001).", "Staff code does not match standard TVC format (e.g. TVC00001).", "社員番号の形式が正しくありません（例：TVC00001）。")
    if "smallint out of range" in m or "numericvalueoutofrange" in m.lower():
        return _tr("Giá trị số nhập vào vượt quá giới hạn cho phép.", "Numeric value is out of allowable range.", "入力された数値が許容範囲を超えています。")

    if "unique constraint" in m.lower() or "uniqueviolation" in m.lower() or "uq_" in m:
        # Kiểm tra các ràng buộc one_open_per (đang có hiệu lực chưa kết thúc)
        if "uq_open_license_assignments_license_id_asset_id" in m or ("license_assignments" in m and "asset_id" in m):
            return _tr(
                "Thiết bị này đã được gán gói bản quyền này từ trước (chưa thu hồi). Một thiết bị không thể nhận 2 bản quyền cùng loại cùng lúc. Vui lòng cập nhật Ngày thu hồi (removed_at) ở lượt gán trước trước khi gán lại.",
                "This device already has an active assignment for this license. Please record the removal date on the existing assignment before reassigning.",
                "この機器にはすでにこのライセンスが割り当てられています（未返却）。再割り当てする前に回収日を入力してください。",
            )
        if "uq_open_license_assignments_license_id_person_id" in m or ("license_assignments" in m and "person_id" in m):
            return _tr(
                "Nhân sự này đã được gán gói bản quyền này từ trước (chưa thu hồi). Một nhân sự không thể nhận 2 bản quyền cùng loại cùng lúc. Vui lòng cập nhật Ngày thu hồi (removed_at) ở lượt gán trước trước khi gán lại.",
                "This person already has an active assignment for this license. Please record the removal date on the existing assignment before reassigning.",
                "この担当者にはすでにこのライセンスが割り当てられています（未返却）。再割り当てする前に回収日を入力してください。",
            )
        if "uq_open_assignments_asset_id" in m or ("assignments" in m and "asset_id" in m):
            return _tr(
                "Thiết bị này hiện đang được bàn giao cho nhân viên khác sử dụng (chưa thu hồi). Vui lòng cập nhật Ngày thu hồi ở lượt bàn giao trước đó trước khi bàn giao lại.",
                "This asset is currently in use and has not been returned yet. Please record the return date before reassigning.",
                "この機器は現在他の担当者に貸出中です（未返却）。再貸出する前に前回の返却日を入力してください。",
            )
        if "uq_open_card_loans_card_id" in m or ("card_loans" in m and "card_id" in m):
            return _tr(
                "Thẻ này hiện đang có người mượn chưa trả. Vui lòng cập nhật Ngày trả ở lượt mượn trước đó trước khi cho người khác mượn.",
                "This access card is currently borrowed and has not been returned yet. Please record the return date before loaning it out again.",
                "このカードは現在貸出中です（未返却）。再貸出する前に前回の返却日を入力してください。",
            )

        if "serial" in m:
            return _tr("Số Serial này đã tồn tại trong hệ thống (bị trùng lặp).", "Serial number already exists in system.", "このシリアル番号はすでにシステムに存在します。")
        if "asset_code" in m:
            return _tr("Mã tài sản này đã tồn tại trong hệ thống (bị trùng lặp).", "Asset code already exists in system.", "この資産コードはすでにシステムに存在します。")
        if "vendor_code" in m:
            return _tr("Mã Vendor này đã tồn tại trong hệ thống (bị trùng lặp).", "Vendor code already exists in system.", "このベンダーコードはすでにシステムに存在します。")
        if "card_no" in m:
            return _tr("Số thẻ này đã tồn tại trong hệ thống (bị trùng lặp).", "Card number already exists in system.", "このカード番号はすでにシステムに存在します。")
        if "staff_code" in m:
            return _tr("Mã nhân viên này đã tồn tại trong hệ thống (bị trùng lặp).", "Staff code already exists in system.", "この社員番号はすでにシステムに存在します。")
        if "user_login_id" in m:
            return _tr("Tài khoản đăng nhập này đã được liên kết với nhân sự khác.", "Login account already linked to another person.", "このログインアカウントはすでに別の社員に紐付けられています。")
        if "username" in m:
            return _tr("Tên đăng nhập này đã tồn tại trong hệ thống (bị trùng lặp).", "Username already exists in system.", "このユーザー名はすでにシステムに存在します。")
        if "device_name" in m:
            return _tr("Tên thiết bị thoại này đã tồn tại trong hệ thống (bị trùng lặp).", "Phone device name already exists in system.", "この電話機器名はすでにシステムに存在します。")
        return _tr("Dữ liệu bị trùng lặp với bản ghi đã tồn tại trong hệ thống.", "Record already exists in system (duplicate).", "システム内に重複するデータが存在します。")

    if "foreign key" in m.lower() or "foreignkeyviolation" in m.lower():
        return _tr("Không thể lưu hoặc xóa vì dữ liệu đang được liên kết với bản ghi khác.", "Cannot save or delete because data is referenced elsewhere.", "他のデータから参照されているため、保存または削除できません。")
    if "not-null constraint" in m.lower() or "notnullviolation" in m.lower():
        return _tr("Vui lòng nhập đầy đủ các trường thông tin bắt buộc.", "Please fill in all required fields.", "必須項目をすべて入力してください。")

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

    def __init__(self) -> None:
        merged = {**DEFAULT_ADMIN_COLUMN_LABELS, **(getattr(self, "column_labels", None) or {})}
        self.column_labels = merged
        super().__init__()

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
            before_data["delete_reason"] = delete_reason

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
                    extra={"delete_reason": delete_reason},
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
                    extra={"delete_reason": delete_reason},
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
    column_labels = {
        "username": "Tên đăng nhập",
        "display_name": "Tên hiển thị",
        "role": "Vai trò hệ thống",
        "preferred_lang": "Ngôn ngữ ưa thích",
        "is_active": "Kích hoạt",
        "last_login_at": "Đăng nhập lần cuối",
    }
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
                description="Admin có thể đặt lại mật khẩu mới cho tài khoản tại đây. Để trống nếu giữ nguyên mật khẩu cũ.",
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
                pwd_clean = str(raw_password).strip()
                if len(pwd_clean) < 6:
                    raise ValueError("Mật khẩu mới phải có độ dài tối thiểu 6 ký tự.")
                data["password_hash"] = hash_password(pwd_clean)

        await super().on_model_change(data, model, is_created, request)


class RoleAdmin(BaseAdminView, model=Role):
    name = "Vai trò"
    name_plural = "Vai trò Hệ thống"
    icon = "fa-solid fa-user-shield"
    category = "Hệ thống & Phân quyền"
    column_list = [Role.id, Role.code, Role.name_en, Role.name_ja]
    column_labels = {
        "code": "Mã vai trò",
        "name_en": "Tên vai trò (Tiếng Anh/Việt)",
        "name_ja": "Tên vai trò (Tiếng Nhật)",
    }
    form_columns = [Role.code, Role.name_en, Role.name_ja]


class RolePermissionAdmin(BaseAdminView, model=RolePermission):
    name = "Quyền vai trò"
    name_plural = "Ma trận Quyền Vai trò"
    icon = "fa-solid fa-key"
    category = "Hệ thống & Phân quyền"
    list_template = "sqladmin/role_permission_matrix.html"
    column_list = [RolePermission.id, RolePermission.role, RolePermission.module, RolePermission.action]
    column_labels = {
        "role": "Vai trò",
        "module": "Phân hệ nghiệp vụ",
        "action": "Thao tác",
    }

    def get_matrix_payload(self) -> dict[str, Any]:
        """Trả về cấu trúc dữ liệu ma trận quyền vai trò trực quan."""
        from app.core.permissions import get_role_permission_matrix

        with SessionLocal() as db:
            return get_role_permission_matrix(db)


class UserPermissionOverrideAdmin(BaseAdminView, model=UserPermissionOverride):
    name = "Ghi đè quyền"
    name_plural = "Quyền riêng Người dùng"
    icon = "fa-solid fa-user-pen"
    category = "Hệ thống & Phân quyền"
    column_list = [UserPermissionOverride.id, UserPermissionOverride.user_id, UserPermissionOverride.module, UserPermissionOverride.action, UserPermissionOverride.granted]
    column_labels = {
        "user_id": "Người dùng",
        "module": "Phân hệ nghiệp vụ",
        "action": "Thao tác",
        "granted": "Được cấp quyền",
    }


class DepartmentAdmin(BaseAdminView, model=Department):
    name = "Phòng ban"
    name_plural = "Danh mục Phòng ban"
    icon = "fa-solid fa-sitemap"
    category = "Danh mục Dùng chung"
    column_list = [Department.id, Department.code, Department.name_en, Department.name_ja]
    column_labels = {
        "code": "Mã phòng ban",
        "name_en": "Tên phòng ban (Tiếng Anh/Việt)",
        "name_ja": "Tên phòng ban (Tiếng Nhật)",
    }


class AssetCategoryAdmin(BaseAdminView, model=AssetCategory):
    name = "Loại tài sản"
    name_plural = "Danh mục Loại tài sản"
    icon = "fa-solid fa-tags"
    category = "Danh mục Dùng chung"
    column_list = [AssetCategory.id, AssetCategory.name_en, AssetCategory.name_ja]
    column_labels = {
        "name_en": "Tên loại tài sản (Tiếng Anh/Việt)",
        "name_ja": "Tên loại tài sản (Tiếng Nhật)",
    }


class AssetTagAdmin(BaseAdminView, model=AssetTag):
    name = "Nhãn tài sản"
    name_plural = "Danh mục Nhãn (Tags)"
    icon = "fa-solid fa-tag"
    category = "Danh mục Dùng chung"
    column_list = [AssetTag.id, AssetTag.code, AssetTag.name_en, AssetTag.color]
    column_labels = {
        "code": "Mã nhãn",
        "name_en": "Tên nhãn (Tiếng Anh/Việt)",
        "name_ja": "Tên nhãn (Tiếng Nhật)",
        "color": "Màu nhãn",
    }


class LocationAdmin(BaseAdminView, model=Location):
    name = "Vị trí / Phòng"
    name_plural = "Danh mục Vị trí"
    icon = "fa-solid fa-location-dot"
    category = "Danh mục Dùng chung"
    column_list = [Location.id, Location.building, Location.floor, Location.room_en, Location.room_ja, Location.is_access_controlled]
    column_labels = {
        "building": "Tòa nhà",
        "floor": "Tầng",
        "room_en": "Phòng (EN)",
        "room_ja": "Phòng (JA)",
        "is_access_controlled": "Kiểm soát thẻ",
        "description": "Mô tả vị trí",
    }


class PersonAdmin(BaseAdminView, model=Person):
    name = "Nhân sự"
    name_plural = "Hồ sơ Nhân sự"
    icon = "fa-solid fa-id-card-clip"
    category = "Nhân sự"
    column_list = [Person.id, Person.staff_code, Person.full_name, Person.department, Person.status, Person.email, Person.start_working_date]
    column_searchable_list = [Person.staff_code, Person.full_name, Person.email]
    column_labels = {
        "staff_code": "Mã nhân viên",
        "full_name": "Họ và tên nhân viên",
        "department": "Phòng ban",
        "status": "Tình trạng",
        "email": "Email",
        "start_working_date": "Ngày vào làm việc",
        "user_login_id": "Tài khoản đăng nhập",
    }
    form_excluded_columns = COMMON_EXCLUDED_COLUMNS + ["secret", "assignments"]


class PersonSecretAdmin(BaseAdminView, model=PersonSecret):
    name = "Mật khẩu nhân viên"
    name_plural = "Kho Mật khẩu Nhân sự"
    icon = "fa-solid fa-user-lock"
    category = "Nhân sự"
    list_template = "sqladmin/person_secrets.html"
    can_create = False
    can_edit = False
    can_delete = False
    can_export = False
    column_list = [PersonSecret.person_id]

    def get_secrets_payload(self) -> list[dict[str, Any]]:
        """Trả về danh sách nhân sự và trạng thái mật khẩu (tuyệt đối không chứa dữ liệu mã hoá *_enc)."""
        from sqlalchemy.orm import selectinload

        with SessionLocal() as db:
            persons = db.scalars(
                select(Person)
                .options(selectinload(Person.department), selectinload(Person.secret))
                .where(Person.is_deleted.is_(False))
                .order_by(Person.staff_code)
            ).all()

            result: list[dict[str, Any]] = []
            for p in persons:
                sec = p.secret
                result.append(
                    {
                        "id": p.id,
                        "staff_code": p.staff_code,
                        "full_name": p.full_name,
                        "department": p.department.name_en if p.department else "-",
                        "department_ja": p.department.name_ja if p.department else "-",
                        "email": p.email or "-",
                        "status": p.status.value if hasattr(p.status, "value") else str(p.status),
                        "has_pc_password": bool(sec and sec.pc_password_enc is not None),
                        "pc_password_note": sec.pc_password_note if sec else "",
                        "has_email_password": bool(sec and sec.email_password_enc is not None),
                        "email_password_note": sec.email_password_note if sec else "",
                        "updated_at": sec.updated_at.strftime("%d/%m/%Y %H:%M") if sec and sec.updated_at else "",
                    }
                )
            return result


class AssetAdmin(BaseAdminView, model=Asset):
    name = "Tài sản IT"
    name_plural = "Danh sách Thiết bị"
    icon = "fa-solid fa-laptop"
    category = "Tài sản"
    column_list = [
        Asset.id,
        Asset.asset_code,
        Asset.vendor_code,
        Asset.serial,
        Asset.category,
        Asset.status,
        "current_holder",
        Asset.model,
    ]
    column_labels = {
        "current_holder": "Người đang sử dụng",
        "asset_code": "Mã GA",
        "vendor_code": "Mã KDDI",
        "serial": "Số Serial",
        "status": "Trạng thái",
        "model": "Model thiết bị",
    }
    column_formatters = {
        "current_holder": lambda m, a: m.current_holder or "-",
    }
    column_searchable_list = [Asset.asset_code, Asset.serial, Asset.vendor_code, Asset.model]
    form_excluded_columns = COMMON_EXCLUDED_COLUMNS + ["assignments"]

    def list_query(self, request: Request) -> Select:
        stmt = super().list_query(request)
        return stmt.options(
            selectinload(Asset.assignments).selectinload(Assignment.person)
        )


class AssignmentAdmin(BaseAdminView, model=Assignment):
    name = "Bàn giao thiết bị"
    name_plural = "Lịch sử Cấp phát Tài sản"
    icon = "fa-solid fa-handshake"
    category = "Tài sản"
    can_delete = False
    column_list = [Assignment.id, Assignment.asset, Assignment.person, Assignment.borrowed_at, Assignment.returned_at]
    column_labels = {
        "asset": "Thiết bị",
        "person": "Nhân viên nhận máy",
        "borrowed_at": "Thời điểm cấp phát",
        "returned_at": "Thời điểm thu hồi",
        "note": "Ghi chú cấp phát",
    }

    async def after_model_change(
        self, data: dict, model: Any, is_created: bool, request: Request
    ) -> None:
        await super().after_model_change(data, model, is_created, request)
        asset_id = getattr(model, "asset_id", None)
        if asset_id:
            try:
                with SessionLocal() as db:
                    asset = db.get(Asset, asset_id)
                    if asset:
                        active_asgn = db.scalar(
                            select(Assignment).where(
                                Assignment.asset_id == asset.id,
                                Assignment.returned_at.is_(None),
                                Assignment.is_deleted.is_(False),
                            )
                        )
                        if active_asgn:
                            asset.status = AssetStatus.IN_USE
                        elif asset.status == AssetStatus.IN_USE:
                            asset.status = AssetStatus.IN_STOCK
                        db.commit()
            except Exception:
                pass


class LicenseProductAdmin(BaseAdminView, model=LicenseProduct):
    name = "Sản phẩm License"
    name_plural = "Danh mục Phần mềm"
    icon = "fa-solid fa-compact-disc"
    category = "License"
    column_list = [LicenseProduct.id, LicenseProduct.name, LicenseProduct.vendor]
    column_labels = {
        "name": "Tên phần mềm",
        "vendor": "Hãng phát triển / Nhà cung cấp",
        "license_type": "Loại bản quyền",
    }


class LicenseAdmin(BaseAdminView, model=License):
    name = "Bản quyền License"
    name_plural = "Kho License Phần mềm"
    icon = "fa-solid fa-certificate"
    category = "License"
    column_list = [
        License.id,
        License.product,
        License.seats,
        "assigned_seats",
        "remaining_seats",
        License.start_date,
        License.expiry_date,
    ]
    column_details_list = [
        License.id,
        License.product,
        License.seats,
        "assigned_seats",
        "remaining_seats",
        License.start_date,
        License.expiry_date,
        License.contract_id,
        License.note,
    ]
    column_labels = {
        "product": "Sản phẩm phần mềm",
        "seats": "Tổng số bản quyền (Seats)",
        "assigned_seats": "Đã cấp phát",
        "remaining_seats": "Còn trống",
        "start_date": "Ngày kích hoạt",
        "expiry_date": "Ngày hết hạn",
        "contract_id": "Hợp đồng mua sắm",
        "note": "Ghi chú",
    }
    column_formatters = {
        "assigned_seats": lambda m, a: Markup(
            f'<span class="badge bg-primary text-white fs-6 px-2 py-1"><i class="fa-solid fa-user-check me-1"></i>{m.assigned_seats}</span>'
        ),
        "remaining_seats": lambda m, a: (
            Markup(
                f'<span class="badge bg-danger text-white fs-6 px-2 py-1"><i class="fa-solid fa-triangle-exclamation me-1"></i>{m.remaining_seats} (Vượt định mức)</span>'
            )
            if m.remaining_seats < 0
            else Markup(
                '<span class="badge bg-secondary text-white fs-6 px-2 py-1">0 (Hết chỗ)</span>'
            )
            if m.remaining_seats == 0
            else Markup(
                f'<span class="badge bg-success text-white fs-6 px-2 py-1"><i class="fa-solid fa-check me-1"></i>{m.remaining_seats}</span>'
            )
        ),
    }
    column_formatters_detail = {
        "assigned_seats": lambda m, a: Markup(
            f'<span class="badge bg-primary text-white fs-6 px-2 py-1"><i class="fa-solid fa-user-check me-1"></i>{m.assigned_seats}</span>'
        ),
        "remaining_seats": lambda m, a: (
            Markup(
                f'<span class="badge bg-danger text-white fs-6 px-2 py-1"><i class="fa-solid fa-triangle-exclamation me-1"></i>{m.remaining_seats} (Vượt định mức)</span>'
            )
            if m.remaining_seats < 0
            else Markup(
                '<span class="badge bg-secondary text-white fs-6 px-2 py-1">0 (Hết chỗ)</span>'
            )
            if m.remaining_seats == 0
            else Markup(
                f'<span class="badge bg-success text-white fs-6 px-2 py-1"><i class="fa-solid fa-check me-1"></i>{m.remaining_seats}</span>'
            )
        ),
    }
    form_excluded_columns = COMMON_EXCLUDED_COLUMNS + ["license_key_enc", "key_version", "assignments"]

    def list_query(self, request: Request) -> Select:
        stmt = super().list_query(request)
        return stmt.options(selectinload(License.assignments))

    async def get_object_for_details(self, value: Any) -> Any:
        stmt = self._stmt_by_identifier(value)
        stmt = stmt.options(selectinload(License.assignments))
        for relation in self._details_relations:
            stmt = stmt.options(selectinload(relation))
        return await self._get_object_by_pk(stmt)


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
    column_labels = {
        "license": "Bản quyền phần mềm",
        "asset": "Thiết bị được gán",
        "person": "Nhân viên được gán",
        "assigned_at": "Thời điểm gán",
        "expiry_date": "Ngày hết hạn",
        "removed_at": "Thời điểm thu hồi",
        "note": "Ghi chú",
    }
    form_columns = [
        "license",
        "asset",
        "person",
        "assigned_at",
        "expiry_date",
        "removed_at",
        "note",
    ]

    def list_query(self, request: Request) -> Select:
        stmt = super().list_query(request)
        return stmt.options(
            selectinload(LicenseAssignment.license),
            selectinload(LicenseAssignment.asset),
            selectinload(LicenseAssignment.person),
        )


class AccessCardAdmin(BaseAdminView, model=AccessCard):
    name = "Thẻ ra vào"
    name_plural = "Danh sách Thẻ từ"
    icon = "fa-solid fa-address-card"
    category = "Thẻ ra vào"
    column_list = [
        AccessCard.id,
        AccessCard.card_no,
        AccessCard.card_type,
        AccessCard.status,
        "current_borrower",
        AccessCard.note,
    ]
    column_labels = {
        "current_borrower": "Người đang giữ thẻ",
        "card_no": "Số thẻ",
        "card_type": "Loại thẻ",
        "status": "Trạng thái",
        "note": "Ghi chú",
    }
    column_formatters = {
        "current_borrower": lambda m, a: m.current_borrower or "-",
    }
    form_excluded_columns = COMMON_EXCLUDED_COLUMNS + ["loans"]

    def list_query(self, request: Request) -> Select:
        stmt = super().list_query(request)
        return stmt.options(
            selectinload(AccessCard.loans).selectinload(CardLoan.person)
        )

    async def on_model_change(
        self, data: dict, model: Any, is_created: bool, request: Request
    ) -> None:
        await super().on_model_change(data, model, is_created, request)
        status_val = data.get("status")
        if status_val in (CardStatus.BORROWED, CardStatus.BORROWED.value, "BORROWED"):
            if is_created:
                raise ValueError(
                    "Không thể đặt trạng thái 'BORROWED' khi tạo mới thẻ vật lý. "
                    "Thẻ mới nhập kho phải là 'IN_STOCK'. "
                    "Để cho mượn thẻ, vui lòng ghi nhận tại mục 'Sổ Mượn-Trả Thẻ'."
                )
            else:
                card_id = getattr(model, "id", None)
                if card_id:
                    with SessionLocal() as db:
                        has_open = db.scalar(
                            select(CardLoan).where(
                                CardLoan.card_id == card_id,
                                CardLoan.returned_at.is_(None),
                                CardLoan.is_deleted.is_(False),
                            )
                        )
                        if not has_open:
                            raise ValueError(
                                "Không thể chuyển trạng thái thẻ sang 'BORROWED' khi chưa có phiếu mượn. "
                                "Vui lòng ghi nhận người mượn tại mục 'Sổ Mượn-Trả Thẻ'."
                            )
        elif not is_created and status_val in (CardStatus.IN_STOCK, CardStatus.IN_STOCK.value, "IN_STOCK"):
            card_id = getattr(model, "id", None)
            if card_id:
                with SessionLocal() as db:
                    has_open = db.scalar(
                        select(CardLoan).where(
                            CardLoan.card_id == card_id,
                            CardLoan.returned_at.is_(None),
                            CardLoan.is_deleted.is_(False),
                        )
                    )
                    if has_open:
                        raise ValueError(
                            "Thẻ này đang có người mượn chưa trả trong 'Sổ Mượn-Trả Thẻ'. "
                            "Vui lòng vào 'Sổ Mượn-Trả Thẻ' cập nhật Ngày trả (returned_at) để hoàn tất thủ tục trả thẻ."
                        )


class CardLoanAdmin(BaseAdminView, model=CardLoan):
    name = "Mượn thẻ từ"
    name_plural = "Sổ Mượn-Trả Thẻ"
    icon = "fa-solid fa-clock-rotate-left"
    category = "Thẻ ra vào"
    can_delete = False
    column_list = [
        CardLoan.id,
        CardLoan.card,
        CardLoan.person,
        CardLoan.external_name,
        CardLoan.borrowed_at,
        CardLoan.returned_at,
    ]
    column_labels = {
        "card": "Thẻ mượn",
        "person": "Nhân viên mượn",
        "external_name": "Người mượn ngoài",
        "external_company": "Đơn vị mượn ngoài",
        "purpose": "Mục đích mượn",
        "borrowed_at": "Thời điểm mượn",
        "expected_return_at": "Dự kiến ngày trả",
        "returned_at": "Thời điểm trả",
    }

    async def on_model_change(
        self, data: dict, model: Any, is_created: bool, request: Request
    ) -> None:
        await super().on_model_change(data, model, is_created, request)
        card_val = data.get("card")
        if card_val is not None:
            cid = getattr(card_val, "id", None)
            if cid is None and str(card_val).isdigit():
                cid = int(card_val)
            if cid and is_created and data.get("returned_at") is None:
                with SessionLocal() as db:
                    card = db.get(AccessCard, cid)
                    if card and card.status in (CardStatus.LOST, CardStatus.DAMAGED):
                        raise ValueError(
                            f"Thẻ '{card.card_no}' đang ở trạng thái {card.status.value}, không thể cho mượn."
                        )

    async def after_model_change(
        self, data: dict, model: Any, is_created: bool, request: Request
    ) -> None:
        await super().after_model_change(data, model, is_created, request)
        card_id = getattr(model, "card_id", None)
        if card_id:
            try:
                with SessionLocal() as db:
                    card = db.get(AccessCard, card_id)
                    if card:
                        active_loan = db.scalar(
                            select(CardLoan).where(
                                CardLoan.card_id == card.id,
                                CardLoan.returned_at.is_(None),
                                CardLoan.is_deleted.is_(False),
                            )
                        )
                        if active_loan:
                            card.status = CardStatus.BORROWED
                        elif card.status == CardStatus.BORROWED:
                            card.status = CardStatus.IN_STOCK
                        db.commit()
            except Exception:
                pass



class ContractAdmin(BaseAdminView, model=Contract):
    name = "Hợp đồng"
    name_plural = "Hợp đồng Mua sắm IT"
    icon = "fa-solid fa-file-contract"
    category = "Hợp đồng"
    column_list = [Contract.id, Contract.code, Contract.vendor_name, Contract.signed_date, Contract.delivery_status]
    column_labels = {
        "code": "Số hợp đồng",
        "vendor_name": "Nhà cung cấp",
        "signed_date": "Ngày ký hợp đồng",
        "delivery_status": "Tiến độ giao hàng",
    }
    form_excluded_columns = COMMON_EXCLUDED_COLUMNS + ["lines"]


class ContractLineAdmin(BaseAdminView, model=ContractLine):
    name = "Hạng mục Hợp đồng"
    name_plural = "Chi tiết Hạng mục"
    icon = "fa-solid fa-list-check"
    category = "Hợp đồng"
    column_list = [ContractLine.id, ContractLine.contract, ContractLine.item_type, ContractLine.qty_ordered]
    column_labels = {
        "contract": "Hợp đồng",
        "item_type": "Hạng mục hàng hóa",
        "spec": "Thông số kỹ thuật",
        "qty_ordered": "Số lượng đặt",
    }
    form_excluded_columns = COMMON_EXCLUDED_COLUMNS + ["assets"]


class PhoneAdmin(BaseAdminView, model=Phone):
    name = "Thiết bị Thoại"
    name_plural = "Danh bạ & Thiết bị Điện thoại"
    icon = "fa-solid fa-phone"
    category = "Danh bạ thoại"
    column_list = [Phone.id, Phone.extension_number, Phone.device_name, Phone.device_type, Phone.location, Phone.is_active]
    column_labels = {
        "device_name": "Tên máy điện thoại",
        "device_type": "Loại điện thoại",
        "extension_number": "Số máy nhánh (Ext)",
        "location": "Vị trí đặt",
        "is_active": "Trạng thái hoạt động",
        "remarks": "Ghi chú",
    }


class AuditLogAdmin(BaseAdminView, model=AuditLog):
    name = "Nhật ký kiểm toán"
    name_plural = "Audit Trail (Bất biến)"
    icon = "fa-solid fa-shield-halved"
    category = "Truy vết"
    can_create = False
    can_edit = False
    can_delete = False
    column_list = [
        AuditLog.id,
        AuditLog.created_at,
        AuditLog.user,
        AuditLog.action,
        AuditLog.table_name,
        AuditLog.record_id,
        "summary",
        AuditLog.ip_address,
    ]
    column_details_list = [
        AuditLog.id,
        AuditLog.created_at,
        AuditLog.user,
        AuditLog.action,
        AuditLog.table_name,
        AuditLog.record_id,
        "summary",
        AuditLog.ip_address,
        AuditLog.before_after,
    ]
    column_labels = {
        "id": "ID",
        "created_at": "Thời gian",
        "user": "Người thực hiện",
        "action": "Hành động",
        "table_name": "Bảng",
        "record_id": "Mã bản ghi",
        "summary": "Chi tiết / Lý do",
        "ip_address": "Địa chỉ IP",
        "before_after": "Dữ liệu trước & sau",
    }
    column_sortable_list = [
        AuditLog.id,
        AuditLog.created_at,
        AuditLog.action,
        AuditLog.table_name,
        AuditLog.record_id,
    ]
    column_default_sort = [(AuditLog.created_at, True)]
    column_searchable_list = [
        AuditLog.table_name,
        AuditLog.action,
        AuditLog.ip_address,
    ]
    column_formatters = {
        "summary": lambda m, a: m.summary or "-",
    }
    column_formatters_detail = {
        "summary": lambda m, a: m.summary or "-",
    }

    def list_query(self, request: Request) -> Select:
        stmt = super().list_query(request)
        stmt = stmt.options(selectinload(AuditLog.user))
        act = request.query_params.get("action")
        if act:
            stmt = stmt.where(AuditLog.action == act)
        tbl = request.query_params.get("table")
        if tbl:
            stmt = stmt.where(AuditLog.table_name == tbl)
        return stmt

    def count_query(self, request: Request) -> Select:
        stmt = super().count_query(request)
        act = request.query_params.get("action")
        if act:
            stmt = stmt.where(AuditLog.action == act)
        tbl = request.query_params.get("table")
        if tbl:
            stmt = stmt.where(AuditLog.table_name == tbl)
        return stmt


BASE_DIR = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = BASE_DIR / "templates"


class TokuyamaAdmin(Admin):
    def get_save_redirect_url(
        self, request: Request, form: FormData, model_view: ModelView, obj: Any
    ) -> str | URL:
        """Điều hướng sau khi Lưu trên form create/edit:
        - 'Lưu và thêm mới' ('Save and add another'): chuyển đến form tạo mới (admin:create).
        - 'Lưu và tiếp tục sửa' ('Save and continue editing'): ở lại trang sửa (admin:edit).
        - 'Lưu' / 'Lưu thay đổi' ('Save') hoặc bất kỳ trường hợp nào khác: BẮT BUỘC quay về danh sách (admin:list).
        """
        identity = request.path_params["identity"]
        save_action = str(form.get("save", "")).strip().lower()

        if "add another" in save_action or "thêm mới" in save_action:
            return request.url_for("admin:create", identity=identity)
        elif "continue editing" in save_action or "tiếp tục sửa" in save_action:
            identifier = get_object_identifier(obj)
            return request.url_for("admin:edit", identity=identity, pk=identifier)
        return request.url_for("admin:list", identity=identity)

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

    from app.core.i18n import (
        format_datetime_clean,
        get_current_lang,
        get_property_label,
        translate,
    )

    admin.templates.env.globals["t"] = translate
    admin.templates.env.filters["t"] = translate
    admin.templates.env.globals["get_current_lang"] = get_current_lang
    admin.templates.env.globals["humanize_error"] = humanize_error_str
    admin.templates.env.filters["humanize_error"] = humanize_error_str
    admin.templates.env.globals["get_property_label"] = get_property_label
    admin.templates.env.filters["get_property_label"] = get_property_label
    admin.templates.env.globals["format_datetime_clean"] = format_datetime_clean
    admin.templates.env.filters["format_datetime_clean"] = format_datetime_clean

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
