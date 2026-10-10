"""Tích hợp SQLAdmin cho hệ thống quản trị ITAM - Tokuyama Vietnam.

Quy định bảo mật GEMINI.md:
- Chỉ tài khoản có vai trò ADMIN mới được truy cập /admin.
- Tuyệt đối không để lộ các trường nhạy cảm trong REDACTED_FIELDS (pc_password_enc, email_password_enc, license_key_enc, password_hash).
- AuditLog là bảng bất biến: cấm tạo, sửa, xoá trên giao diện (can_create=False, can_edit=False, can_delete=False).
"""

from __future__ import annotations

import contextlib
import contextvars
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
from starlette.types import ASGIApp, Receive, Scope, Send
import time
from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session, joinedload, selectinload
from markupsafe import Markup, escape


from app.core.audit import audit_login, record_audit
from app.core.i18n import DEFAULT_ADMIN_COLUMN_LABELS, get_current_lang, translate
from app.core.permissions import get_user_permissions
from app.core.security import (
    DUMMY_PASSWORD_HASH,
    SESSION_SECRET,
    create_session_token,
    hash_password,
    verify_password,
    verify_session_token,
)
from wtforms import Form, PasswordField, SelectField
from wtforms.widgets import PasswordInput
from app.db import SessionLocal
from app.enums import AssetStatus, AuditAction, CardStatus, Module, PermissionAction, PersonStatus, RoleCode
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
    REDACTED_FIELDS,
    Role,
    RolePermission,
    User,
    UserPermissionOverride,
)
from app.services.contract_service import sync_contract_delivery_status

COMMON_EXCLUDED_COLUMNS = [
    "created_at", "created_by", "updated_at", "updated_by",
    "is_deleted", "deleted_at", "deleted_by", "delete_reason"
]
REDACTED_COLUMNS = sorted(list(REDACTED_FIELDS))

current_request_ctx: contextvars.ContextVar[Request | None] = contextvars.ContextVar("current_request_ctx", default=None)
 
 
def get_admin_lang() -> str:
    """Lấy mã ngôn ngữ hiện tại của request (vi, en, ja)."""
    req = current_request_ctx.get()
    if req:
        return get_current_lang(req)
    return "vi"


@contextlib.contextmanager
def _get_admin_db(request: Request | None):
    """Lấy session DB: ưu tiên Session thật có sẵn trong request.state (ví dụ khi test), ngược lại mở SessionLocal."""
    req_db = getattr(request.state, "db", None) if request and hasattr(request, "state") else None
    if isinstance(req_db, Session):
        yield req_db
    else:
        with SessionLocal() as db:
            yield db


class RequestContextMiddleware:
    """Middleware ASGI lưu giữ Request hiện tại vào ContextVar để hỗ trợ kiểm tra RBAC động trên View."""
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            request = Request(scope, receive)
            token = current_request_ctx.set(request)
            try:
                await self.app(scope, receive, send)
            finally:
                current_request_ctx.reset(token)
        else:
            await self.app(scope, receive, send)


_AUTH_USER_CACHE: dict[int, tuple[float, User]] = {}
_AUTH_USER_CACHE_TTL = 60.0  # 60s in-memory cache for authenticated user & role


def get_cached_user(user_id: int) -> User | None:
    entry = _AUTH_USER_CACHE.get(user_id)
    if entry:
        cached_time, user = entry
        if time.monotonic() - cached_time < _AUTH_USER_CACHE_TTL:
            return user
        _AUTH_USER_CACHE.pop(user_id, None)
    return None


def set_cached_user(user: User) -> None:
    _AUTH_USER_CACHE[user.id] = (time.monotonic(), user)


def invalidate_user_cache(user_id: int | None = None) -> None:
    if user_id is None:
        _AUTH_USER_CACHE.clear()
    else:
        _AUTH_USER_CACHE.pop(user_id, None)


_MODEL_COUNT_CACHE: dict[type, tuple[float, int]] = {}
_MODEL_COUNT_CACHE_TTL = 30.0  # 30s cache cho số lượng bản ghi để tiết kiệm roundtrip Aiven Cloud


def invalidate_model_count_cache(model: type | None = None) -> None:
    """Xóa cache số lượng bản ghi khi có thao tác thêm, xóa, sửa hoặc khôi phục."""
    if model is None:
        _MODEL_COUNT_CACHE.clear()
    else:
        _MODEL_COUNT_CACHE.pop(model, None)


def get_user_from_request(request: Request, db: Any) -> User | None:
    """Trích xuất và cache thông tin User từ request để tránh truy vấn lặp lại."""
    if hasattr(request.state, "current_user") and request.state.current_user is not None:
        return request.state.current_user

    user_id = request.session.get("user_id") if hasattr(request, "session") else None
    if not user_id:
        token = request.cookies.get("itam_session")
        if token:
            payload = verify_session_token(token)
            if payload and "user_id" in payload:
                user_id = payload["user_id"]

    if not user_id:
        return None

    cached = get_cached_user(int(user_id))
    if cached:
        request.state.current_user = cached
        return cached

    user = db.scalar(
        select(User).options(joinedload(User.role)).where(
            User.id == int(user_id),
            User.is_active.is_(True),
            User.is_deleted.is_(False),
        )
    )
    if user:
        set_cached_user(user)
    request.state.current_user = user
    return user


def get_user_permissions_cached(request: Request, db: Any, user: User) -> set[tuple[str, str]]:
    """Cache tập hợp quyền (module, action) của user trên scope request."""
    if not hasattr(request.state, "user_perms_set"):
        request.state.user_perms_set = get_user_permissions(db, user)
    return request.state.user_perms_set


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
                select(User).options(joinedload(User.role)).where(
                    User.username == username,
                    User.is_active.is_(True),
                    User.is_deleted.is_(False),
                )
            )
            valid_password = False
            if user:
                valid_password = verify_password(password, user.password_hash)
            else:
                verify_password(password, DUMMY_PASSWORD_HASH)

            if user and valid_password:
                user.last_login_at = dt.datetime.now(dt.timezone.utc)
                audit_login(db, user_id=user.id, success=True, username=username, ip_address=client_ip)
                db.commit()

                set_cached_user(user)

                role_code = user.role.code if user.role else RoleCode.ADMIN.value
                token = create_session_token({
                    "user_id": user.id,
                    "role": role_code,
                    "username": user.username,
                })
                lang = user.preferred_lang or request.cookies.get("itam_lang") or "vi"

                if role_code == RoleCode.ADMIN.value:
                    role_title = "ADMINISTRATOR"
                elif role_code == RoleCode.GA_MANAGER.value:
                    role_title = "GA MANAGER"
                elif role_code == RoleCode.EXECUTIVE.value:
                    role_title = "EXECUTIVE"
                else:
                    role_title = role_code

                request.session.update({
                    "token": token,
                    "user_id": user.id,
                    "role": role_code,
                    "role_code": role_code,
                    "role_title": role_title,
                    "username": user.username,
                    "display_name": user.display_name or user.username,
                    "lang": lang,
                })

                # Điều hướng vào trang quản trị /admin cho cả 3 vai trò
                request.state.redirect_url = "/admin"
                return True
            else:
                request.state.login_error = "Tên đăng nhập hoặc mật khẩu không chính xác."
                audit_login(db, user_id=user.id if user else None, success=False, username=username, ip_address=client_ip)
                db.commit()

        return False

    async def logout(self, request: Request) -> bool:
        user_id = request.session.get("user_id")
        if user_id:
            invalidate_user_cache(int(user_id))
        request.session.clear()
        return True

    async def authenticate(self, request: Request) -> bool:
        token = request.session.get("token") or request.cookies.get("itam_session")
        if not token:
            return False

        payload = verify_session_token(token)
        if not payload:
            return False

        user_id = payload.get("user_id")
        if not user_id:
            return False

        user = get_cached_user(int(user_id))
        if not user:
            with SessionLocal() as db:
                user = db.scalar(
                    select(User).options(joinedload(User.role)).where(
                        User.id == int(user_id),
                        User.is_active.is_(True),
                        User.is_deleted.is_(False),
                    )
                )
                if user and user.role:
                    set_cached_user(user)

        if not user or not user.role:
            return False

        role_code = user.role.code
        if role_code not in (RoleCode.ADMIN.value, RoleCode.GA_MANAGER.value, RoleCode.EXECUTIVE.value):
            return False

        if role_code == RoleCode.ADMIN.value:
            role_title = "ADMINISTRATOR"
        elif role_code == RoleCode.GA_MANAGER.value:
            role_title = "GA MANAGER"
        elif role_code == RoleCode.EXECUTIVE.value:
            role_title = "EXECUTIVE"
        else:
            role_title = role_code

        if "lang" not in request.session:
            request.session["lang"] = user.preferred_lang or request.cookies.get("itam_lang") or "vi"

        request.session["user_id"] = user.id
        request.session["username"] = user.username
        request.session["display_name"] = user.display_name or user.username
        request.session["role"] = role_code
        request.session["role_code"] = role_code
        request.session["role_title"] = role_title
        request.state.current_user = user
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
    module: Module | None = None
    can_export = True
    page_size = 25
    page_size_options = [10, 25, 50, 100]
    form_excluded_columns = COMMON_EXCLUDED_COLUMNS + REDACTED_COLUMNS
    column_export_exclude_list = REDACTED_COLUMNS
    column_details_exclude_list = REDACTED_COLUMNS
    column_exclude_list = REDACTED_COLUMNS

    def __init__(self) -> None:
        merged = {**DEFAULT_ADMIN_COLUMN_LABELS, **(getattr(self, "column_labels", None) or {})}
        self.column_labels = merged
        super().__init__()

    def has_action_permission(self, request: Request, action: PermissionAction) -> bool:
        if self.module is None:
            return True
        with SessionLocal() as db:
            user = get_user_from_request(request, db)
            if not user:
                return False
            if user.role and user.role.code == RoleCode.ADMIN.value:
                return True
            perms = get_user_permissions_cached(request, db, user)
            mod_val = self.module.value if isinstance(self.module, Module) else str(self.module)
            act_val = action.value if isinstance(action, PermissionAction) else str(action)
            return (mod_val, act_val) in perms

    def is_visible(self, request: Request) -> bool:
        if self.module is None:
            return True
        return self.has_action_permission(request, PermissionAction.VIEW)

    def is_accessible(self, request: Request) -> bool:
        if self.module is None:
            return True
        path = request.url.path.lower()
        if "/create" in path:
            action = PermissionAction.ADD
        elif "/edit" in path:
            action = PermissionAction.CHANGE
        elif "/delete" in path:
            action = PermissionAction.DELETE
        else:
            action = PermissionAction.VIEW
        return self.has_action_permission(request, action)

    @property
    def can_create(self) -> bool:
        if getattr(self, "_can_create_override", None) is False:
            return False
        req = current_request_ctx.get()
        if not req:
            return True
        return self.has_action_permission(req, PermissionAction.ADD)

    @property
    def can_edit(self) -> bool:
        if getattr(self, "_can_edit_override", None) is False:
            return False
        req = current_request_ctx.get()
        if not req:
            return True
        return self.has_action_permission(req, PermissionAction.CHANGE)

    @property
    def can_delete(self) -> bool:
        if getattr(self, "_can_delete_override", None) is False:
            return False
        req = current_request_ctx.get()
        if not req:
            return True
        return self.has_action_permission(req, PermissionAction.DELETE)

    async def insert_model(self, request: Request, data: dict) -> Any:
        try:
            res = await super().insert_model(request, data)
            invalidate_model_count_cache(self.model)
            return res
        except Exception as e:
            lang = request.session.get("lang", "vi")
            raise ValueError(humanize_error_str(str(e), lang=lang)) from e

    async def update_model(self, request: Request, pk: Any, data: dict) -> Any:
        try:
            res = await super().update_model(request, pk, data)
            invalidate_model_count_cache(self.model)
            return res
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

    async def count(self, request: Request, stmt: Select | None = None) -> int:
        """Đếm số bản ghi với cache RAM (TTL 30s) cho danh sách mặc định không filter.

        Loại bỏ 1 round-trip SQL (~210ms) tới Aiven Cloud trên mỗi lần bấm đổi tab.
        """
        has_search = bool(request.query_params.get("search"))
        if stmt is None and not has_search:
            cached = _MODEL_COUNT_CACHE.get(self.model)
            if cached:
                cached_time, val = cached
                if time.monotonic() - cached_time < _MODEL_COUNT_CACHE_TTL:
                    return val
            val = await super().count(request, stmt)
            _MODEL_COUNT_CACHE[self.model] = (time.monotonic(), val)
            return val
        return await super().count(request, stmt)

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

        with _get_admin_db(request) as db:
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

            # Chặn xóa Nhân viên khi còn đang giữ thiết bị IT, thẻ ra vào hoặc license
            if self.model is Person:
                active_asgn = db.scalar(
                    select(Assignment).where(
                        Assignment.person_id == obj.id,
                        Assignment.returned_at.is_(None),
                        Assignment.is_deleted.is_(False),
                    )
                )
                if active_asgn:
                    raise HTTPException(
                        status_code=400,
                        detail="Không thể xóa nhân viên đang giữ thiết bị IT. Hãy thu hồi thiết bị trước khi xóa.",
                    )

                active_card = db.scalar(
                    select(CardLoan).where(
                        CardLoan.person_id == obj.id,
                        CardLoan.returned_at.is_(None),
                        CardLoan.is_deleted.is_(False),
                    )
                )
                if active_card:
                    raise HTTPException(
                        status_code=400,
                        detail="Không thể xóa nhân viên đang mượn thẻ ra vào. Hãy thu hồi thẻ trước khi xóa.",
                    )

                active_lic = db.scalar(
                    select(LicenseAssignment).where(
                        LicenseAssignment.person_id == obj.id,
                        LicenseAssignment.removed_at.is_(None),
                        LicenseAssignment.is_deleted.is_(False),
                    )
                )
                if active_lic:
                    raise HTTPException(
                        status_code=400,
                        detail="Không thể xóa nhân viên đang được cấp bản quyền phần mềm. Hãy thu hồi license trước khi xóa.",
                    )

            # Chặn xóa Thiết bị khi đang được sử dụng hoặc có lượt bàn giao mở
            if self.model is Asset:
                active_asgn = db.scalar(
                    select(Assignment).where(
                        Assignment.asset_id == obj.id,
                        Assignment.returned_at.is_(None),
                        Assignment.is_deleted.is_(False),
                    )
                )
                if active_asgn or obj.status == AssetStatus.IN_USE:
                    raise HTTPException(
                        status_code=400,
                        detail="Không thể xóa thiết bị đang có người sử dụng. Hãy thu hồi thiết bị trước khi xóa.",
                    )

            # Chặn xóa Thẻ ra vào khi đang có người mượn
            if self.model is AccessCard:
                active_loan = db.scalar(
                    select(CardLoan).where(
                        CardLoan.card_id == obj.id,
                        CardLoan.returned_at.is_(None),
                        CardLoan.is_deleted.is_(False),
                    )
                )
                if active_loan or obj.status == CardStatus.BORROWED:
                    raise HTTPException(
                        status_code=400,
                        detail="Không thể xóa thẻ ra vào đang có người mượn. Hãy thu hồi thẻ trước khi xóa.",
                    )

            # Chặn xóa dòng hợp đồng nếu đã có thiết bị nhập kho
            if self.model is ContractLine:
                active_asset_count = db.scalar(
                    select(func.count(Asset.id)).where(
                        Asset.contract_line_id == obj.id,
                        Asset.is_deleted.is_(False),
                    )
                ) or 0
                if active_asset_count > 0:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Không thể xóa dòng hợp đồng đã có {active_asset_count} thiết bị nhập kho.",
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

                # Nếu xóa mềm Asset, đồng bộ lại tiến độ hợp đồng liên quan
                if self.model is Asset and getattr(obj, "contract_line_id", None):
                    line = db.get(ContractLine, obj.contract_line_id)
                    if line:
                        sync_contract_delivery_status(db, line.contract_id)

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

            invalidate_model_count_cache(self.model)

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
    module = Module.USERS
    name = "Người dùng"
    name_plural = "Tài khoản Đăng nhập"
    icon = "fa-solid fa-users-gear"
    category = "Hệ thống & Phân quyền"
    column_list = [User.id, User.username, User.display_name, User.role, User.preferred_lang, User.is_active, User.last_login_at]
    column_details_list = [
        User.id,
        User.username,
        User.display_name,
        User.role,
        User.preferred_lang,
        User.is_active,
        User.last_login_at,
    ] + COMMON_EXCLUDED_COLUMNS
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
    module = Module.USERS
    name = "Vai trò"
    name_plural = "Vai trò Hệ thống"
    icon = "fa-solid fa-user-shield"
    category = "Hệ thống & Phân quyền"
    column_list = [Role.id, Role.code, Role.name_en, Role.name_ja]
    column_details_list = [Role.id, Role.code, Role.name_en, Role.name_ja] + COMMON_EXCLUDED_COLUMNS
    column_labels = {
        "code": "Mã vai trò",
        "name_en": "Tên vai trò (Tiếng Anh/Việt)",
        "name_ja": "Tên vai trò (Tiếng Nhật)",
    }
    form_columns = [Role.code, Role.name_en, Role.name_ja]


class RolePermissionAdmin(BaseAdminView, model=RolePermission):
    module = Module.USERS
    name = "Quyền vai trò"
    name_plural = "Ma trận Quyền Vai trò"
    icon = "fa-solid fa-key"
    category = "Hệ thống & Phân quyền"
    list_template = "sqladmin/role_permission_matrix.html"
    column_list = [RolePermission.id, RolePermission.role, RolePermission.module, RolePermission.action]
    column_details_list = [RolePermission.id, RolePermission.role, RolePermission.module, RolePermission.action] + COMMON_EXCLUDED_COLUMNS
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
    module = Module.USERS
    name = "Ghi đè quyền"
    name_plural = "Quyền riêng Người dùng"
    icon = "fa-solid fa-user-pen"
    category = "Hệ thống & Phân quyền"
    column_list = [UserPermissionOverride.id, UserPermissionOverride.user_id, UserPermissionOverride.module, UserPermissionOverride.action, UserPermissionOverride.granted]
    column_details_list = [UserPermissionOverride.id, UserPermissionOverride.user_id, UserPermissionOverride.module, UserPermissionOverride.action, UserPermissionOverride.granted]
    column_labels = {
        "user_id": "Người dùng",
        "module": "Phân hệ nghiệp vụ",
        "action": "Thao tác",
        "granted": "Được cấp quyền",
    }


class DepartmentAdmin(BaseAdminView, model=Department):
    module = Module.PERSONS
    name = "Phòng ban"
    name_plural = "Danh mục Phòng ban"
    icon = "fa-solid fa-sitemap"
    category = "Danh mục Dùng chung"
    column_list = [Department.id, Department.code, Department.name_en, Department.name_ja]
    column_details_list = [Department.id, Department.code, Department.name_en, Department.name_ja] + COMMON_EXCLUDED_COLUMNS
    column_labels = {
        "code": "Mã phòng ban",
        "name_en": "Tên phòng ban (Tiếng Anh/Việt)",
        "name_ja": "Tên phòng ban (Tiếng Nhật)",
    }


class AssetCategoryAdmin(BaseAdminView, model=AssetCategory):
    module = Module.ASSETS
    name = "Loại tài sản"
    name_plural = "Danh mục Loại tài sản"
    icon = "fa-solid fa-tags"
    category = "Danh mục Dùng chung"
    column_list = [AssetCategory.id, AssetCategory.name_en, AssetCategory.name_ja]
    column_details_list = [AssetCategory.id, AssetCategory.name_en, AssetCategory.name_ja] + COMMON_EXCLUDED_COLUMNS
    column_labels = {
        "name_en": "Tên loại tài sản (Tiếng Anh/Việt)",
        "name_ja": "Tên loại tài sản (Tiếng Nhật)",
    }


class AssetTagAdmin(BaseAdminView, model=AssetTag):
    module = Module.ASSETS
    name = "Nhãn tài sản"
    name_plural = "Danh mục Nhãn (Tags)"
    icon = "fa-solid fa-tag"
    category = "Danh mục Dùng chung"
    column_list = [AssetTag.id, AssetTag.code, AssetTag.name_en, AssetTag.color]
    column_details_list = [AssetTag.id, AssetTag.code, AssetTag.name_en, AssetTag.name_ja, AssetTag.color] + COMMON_EXCLUDED_COLUMNS
    column_labels = {
        "code": "Mã nhãn",
        "name_en": "Tên nhãn (Tiếng Anh/Việt)",
        "name_ja": "Tên nhãn (Tiếng Nhật)",
        "color": "Màu nhãn",
    }


class LocationAdmin(BaseAdminView, model=Location):
    module = Module.CARDS
    name = "Vị trí / Phòng"
    name_plural = "Danh mục Vị trí"
    icon = "fa-solid fa-location-dot"
    category = "Danh mục Dùng chung"
    column_list = [Location.id, Location.building, Location.floor, Location.room_en, Location.room_ja, Location.is_access_controlled]
    column_details_list = [
        Location.id,
        Location.building,
        Location.floor,
        Location.room_en,
        Location.room_ja,
        Location.is_access_controlled,
        Location.description,
    ] + COMMON_EXCLUDED_COLUMNS
    column_labels = {
        "building": "Tòa nhà",
        "floor": "Tầng",
        "room_en": "Phòng (EN)",
        "room_ja": "Phòng (JA)",
        "is_access_controlled": "Kiểm soát thẻ",
        "description": "Mô tả vị trí",
    }


class PersonAdmin(BaseAdminView, model=Person):
    module = Module.PERSONS
    name = "Nhân sự"
    name_plural = "Hồ sơ Nhân sự"
    icon = "fa-solid fa-id-card-clip"
    category = "Nhân sự"
    column_list = [Person.id, Person.staff_code, Person.full_name, Person.department, Person.status, Person.email, Person.start_working_date]
    column_details_list = [
        Person.id,
        Person.staff_code,
        Person.full_name,
        Person.department,
        Person.email,
        Person.user_login_id,
        Person.status,
        Person.start_working_date,
        Person.note,
    ] + COMMON_EXCLUDED_COLUMNS
    column_searchable_list = [Person.staff_code, Person.full_name, Person.email]
    column_labels = {
        "staff_code": "Mã nhân viên",
        "full_name": "Họ và tên nhân viên",
        "department": "Phòng ban",
        "status": "Tình trạng",
        "email": "Email",
        "start_working_date": "Ngày vào làm việc",
        "user_login_id": "Tài khoản đăng nhập",
        "note": "Ghi chú",
    }
    column_formatters = {
        "status": lambda m, a: (
            Markup(f'<span class="badge bg-success-subtle text-success border border-success-subtle px-2 py-1"><i class="fa-solid fa-user-check me-1"></i>{translate("Đang làm việc", get_admin_lang())}</span>')
            if m.status == PersonStatus.ACTIVE
            else (
                Markup(f'<span class="badge bg-info-subtle text-info border border-info-subtle px-2 py-1"><i class="fa-solid fa-user-clock me-1"></i>{translate("Sắp vào làm", get_admin_lang())}</span>')
                if m.status == PersonStatus.SCHEDULED
                else Markup(f'<span class="badge bg-secondary text-white px-2 py-1"><i class="fa-solid fa-user-slash me-1"></i>{translate("Đã nghỉ việc", get_admin_lang())}</span>')
            )
        ),
    }
    column_formatters_detail = {
        "status": lambda m, a: (
            Markup(f'<span class="badge bg-success-subtle text-success border border-success-subtle px-2 py-1"><i class="fa-solid fa-user-check me-1"></i>{translate("Đang làm việc", get_admin_lang())} (ACTIVE)</span>')
            if m.status == PersonStatus.ACTIVE
            else (
                Markup(f'<span class="badge bg-info-subtle text-info border border-info-subtle px-2 py-1"><i class="fa-solid fa-user-clock me-1"></i>{translate("Sắp vào làm", get_admin_lang())} (SCHEDULED)</span>')
                if m.status == PersonStatus.SCHEDULED
                else Markup(f'<span class="badge bg-secondary text-white px-2 py-1"><i class="fa-solid fa-user-slash me-1"></i>{translate("Đã nghỉ việc", get_admin_lang())} (RESIGNED)</span>')
            )
        ),
    }
    form_excluded_columns = COMMON_EXCLUDED_COLUMNS + ["secret", "assignments"]

    async def get_object_for_details(self, value: Any) -> Any:
        stmt = self._stmt_by_identifier(value)
        stmt = stmt.options(
            selectinload(Person.department),
            selectinload(Person.assignments)
            .selectinload(Assignment.asset)
            .selectinload(Asset.category),
            selectinload(Person.secret),
        )
        for relation in self._details_relations:
            stmt = stmt.options(selectinload(relation))
        person = await self._get_object_by_pk(stmt)
        if person:
            # 1. Truy vấn các gói License đã cấp phát cho nhân sự này (cấp trực tiếp hoặc qua máy đang giữ)
            active_asset_ids = [
                a.asset_id for a in person.assignments
                if a.returned_at is None and a.asset and not a.asset.is_deleted
            ]
            lic_cond = (LicenseAssignment.person_id == person.id)
            if active_asset_ids:
                lic_cond = or_(
                    LicenseAssignment.person_id == person.id,
                    LicenseAssignment.asset_id.in_(active_asset_ids),
                )

            lic_stmt = (
                select(LicenseAssignment)
                .options(
                    selectinload(LicenseAssignment.license).selectinload(License.product),
                    selectinload(LicenseAssignment.asset),
                )
                .where(
                    lic_cond,
                    LicenseAssignment.is_deleted.is_(False),
                )
                .order_by(LicenseAssignment.assigned_at.desc())
            )
            person.license_assignments = await self._run_query(lic_stmt)

            # 2. Truy vấn các lượt mượn Thẻ ra vào của nhân sự này
            card_stmt = (
                select(CardLoan)
                .options(selectinload(CardLoan.card))
                .where(
                    CardLoan.person_id == person.id,
                    CardLoan.is_deleted.is_(False),
                )
                .order_by(CardLoan.borrowed_at.desc())
            )
            person.card_loans = await self._run_query(card_stmt)

        return person


class PersonSecretAdmin(BaseAdminView, model=PersonSecret):
    module = Module.SECRETS
    name = "Mật khẩu nhân viên"
    name_plural = "Kho Mật khẩu Nhân sự"
    icon = "fa-solid fa-user-lock"
    category = "Nhân sự"
    list_template = "sqladmin/person_secrets.html"
    can_create = False
    can_edit = False
    can_delete = False
    can_export = False
    can_view_details = False
    column_list = [PersonSecret.person_id]
    column_details_list = [PersonSecret.person_id]
    column_export_list = [PersonSecret.person_id]
    form_excluded_columns = COMMON_EXCLUDED_COLUMNS + REDACTED_COLUMNS + [
        "key_version",
        "pc_password_note",
        "email_password_note",
    ]

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
    module = Module.ASSETS
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
        "status_badge",
        "current_holder",
        Asset.model,
        "actions_quick",
    ]
    column_details_list = [
        Asset.id,
        Asset.asset_code,
        Asset.vendor_code,
        Asset.serial,
        Asset.category,
        Asset.status,
        "current_holder",
        Asset.model,
        Asset.form_factor,
        Asset.hwid,
        Asset.mac_ethernet,
        Asset.mac_wifi,
        Asset.contract_line,
        Asset.note,
    ] + COMMON_EXCLUDED_COLUMNS
    column_labels = {
        "status_badge": "Trạng thái",
        "current_holder": "Người đang sử dụng",
        "actions_quick": "Thao tác nhanh",
        "asset_code": "Mã GA",
        "vendor_code": "Mã KDDI",
        "serial": "Số Serial",
        "status": "Trạng thái",
        "model": "Model thiết bị",
    }
    column_formatters = {
        "status_badge": lambda m, a: (
            Markup(f'<span class="badge bg-success-subtle text-success border border-success-subtle px-2 py-1"><i class="fa-solid fa-box-archive me-1"></i>{translate("Trong kho", get_admin_lang())}</span>')
            if m.status == AssetStatus.IN_STOCK
            else (
                Markup(f'<span class="badge bg-primary-subtle text-primary border border-primary-subtle px-2 py-1"><i class="fa-solid fa-user-check me-1"></i>{translate("Đang sử dụng", get_admin_lang())}</span>')
                if m.status == AssetStatus.IN_USE
                else (
                    Markup(f'<span class="badge bg-warning-subtle text-warning border border-warning-subtle px-2 py-1"><i class="fa-solid fa-wrench me-1"></i>{translate("Đang sửa chữa", get_admin_lang())}</span>')
                    if m.status == AssetStatus.REPAIR
                    else (
                        Markup(f'<span class="badge bg-secondary text-white px-2 py-1"><i class="fa-solid fa-trash-can me-1"></i>{translate("Đã thanh lý", get_admin_lang())}</span>')
                        if m.status == AssetStatus.DISPOSED
                        else Markup(f'<span class="badge bg-danger text-white px-2 py-1">{escape(m.status.value if m.status else "-")}</span>')
                    )
                )
            )
        ),
        "current_holder": lambda m, a: (
            Markup(f'<span class="fw-semibold text-dark"><i class="fa-solid fa-user me-1 text-primary"></i>{escape(m.current_holder)}</span>')
            if m.current_holder
            else Markup('<span class="text-muted">-</span>')
        ),
        "actions_quick": lambda m, a: (
            Markup(
                f'<button type="button" class="btn btn-sm btn-outline-primary py-0 px-2 fw-semibold" '
                f'data-id="{m.id}" data-code="{escape(m.asset_code or m.serial or "")}" data-model="{escape(m.model or "")}" '
                f'onclick="openAssignModal(this.dataset.id, this.dataset.code, this.dataset.model)" style="font-size: 11.5px;">'
                f'<i class="fa-solid fa-handshake me-1"></i>{translate("Bàn giao", get_admin_lang())}</button>'
            )
            if m.status == AssetStatus.IN_STOCK
            else (
                Markup(
                    f'<button type="button" class="btn btn-sm btn-outline-warning text-dark py-0 px-2 fw-bold" '
                    f'data-id="{m.id}" data-code="{escape(m.asset_code or m.serial or "")}" data-holder="{escape(m.current_holder or "")}" '
                    f'onclick="openReturnModal(this.dataset.id, this.dataset.code, this.dataset.holder)" style="font-size: 11.5px;">'
                    f'<i class="fa-solid fa-arrow-rotate-left me-1"></i>{translate("Thu hồi", get_admin_lang())}</button>'
                )
                if m.status == AssetStatus.IN_USE
                else Markup('<span class="text-muted small">-</span>')
            )
        ),
    }
    column_formatters_detail = {
        "status": lambda m, a: (
            Markup(f'<span class="badge bg-success-subtle text-success border border-success-subtle px-2 py-1"><i class="fa-solid fa-box-archive me-1"></i>{translate("Trong kho", get_admin_lang())} (IN_STOCK)</span>')
            if m.status == AssetStatus.IN_STOCK
            else (
                Markup(f'<span class="badge bg-primary-subtle text-primary border border-primary-subtle px-2 py-1"><i class="fa-solid fa-user-check me-1"></i>{translate("Đang sử dụng", get_admin_lang())} (IN_USE)</span>')
                if m.status == AssetStatus.IN_USE
                else (
                    Markup(f'<span class="badge bg-warning-subtle text-warning border border-warning-subtle px-2 py-1"><i class="fa-solid fa-wrench me-1"></i>{translate("Đang sửa chữa", get_admin_lang())} (REPAIR)</span>')
                    if m.status == AssetStatus.REPAIR
                    else (
                        Markup(f'<span class="badge bg-secondary text-white px-2 py-1"><i class="fa-solid fa-trash-can me-1"></i>{translate("Đã thanh lý", get_admin_lang())} (DISPOSED)</span>')
                        if m.status == AssetStatus.DISPOSED
                        else Markup(f'<span class="badge bg-danger text-white px-2 py-1">{escape(m.status.value if m.status else "-")}</span>')
                    )
                )
            )
        ),
        "current_holder": lambda m, a: (
            Markup(f'<span class="fw-semibold text-dark"><i class="fa-solid fa-user me-1 text-primary"></i>{escape(m.current_holder)}</span>')
            if m.current_holder
            else Markup(f'<span class="text-muted fst-italic">- ({translate("Trong kho", get_admin_lang())})</span>')
        ),
    }
    column_searchable_list = [Asset.asset_code, Asset.serial, Asset.vendor_code, Asset.model]
    form_excluded_columns = COMMON_EXCLUDED_COLUMNS + ["assignments"]

    def list_query(self, request: Request) -> Select:
        stmt = super().list_query(request)
        return stmt.options(
            selectinload(Asset.assignments).selectinload(Assignment.person)
        )

    async def get_object_for_details(self, value: Any) -> Any:
        stmt = self._stmt_by_identifier(value)
        stmt = stmt.options(
            selectinload(Asset.category),
            selectinload(Asset.contract_line),
            selectinload(Asset.assignments).selectinload(Assignment.person).selectinload(Person.department),
        )
        for relation in self._details_relations:
            stmt = stmt.options(selectinload(relation))
        return await self._get_object_by_pk(stmt)


class AssignmentAdmin(BaseAdminView, model=Assignment):
    module = Module.ASSIGNMENTS
    name = "Bàn giao thiết bị"
    name_plural = "Lịch sử Cấp phát Tài sản"
    icon = "fa-solid fa-handshake"
    category = "Tài sản"
    can_delete = False
    column_list = [
        Assignment.id,
        Assignment.asset,
        Assignment.person,
        "status_badge",
        Assignment.borrowed_at,
        Assignment.returned_at,
        "actions_quick",
    ]
    column_details_list = [
        Assignment.id,
        Assignment.asset,
        Assignment.person,
        "status_badge",
        Assignment.borrowed_at,
        Assignment.returned_at,
        Assignment.note,
    ] + ["created_at", "created_by", "updated_at", "updated_by"]
    column_labels = {
        "asset": "Thiết bị",
        "person": "Nhân viên nhận máy",
        "status_badge": "Trạng thái",
        "borrowed_at": "Thời điểm cấp phát",
        "returned_at": "Thời điểm thu hồi",
        "note": "Ghi chú cấp phát",
        "actions_quick": "Thao tác",
    }
    column_formatters = {
        "status_badge": lambda m, a: (
            Markup(f'<span class="badge bg-secondary text-white"><i class="fa-solid fa-ban me-1"></i>{translate("Đã thu hồi", get_admin_lang())}</span>')
            if m.returned_at
            else Markup(f'<span class="badge bg-success text-white"><i class="fa-solid fa-circle-check me-1"></i>{translate("Đang sử dụng", get_admin_lang())}</span>')
        ),
        "actions_quick": lambda m, a: (
            Markup(
                f'<button type="button" class="btn btn-sm btn-outline-warning text-dark py-0 px-2 fw-bold" '
                f'data-id="{m.asset_id}" data-code="{escape(m.asset.asset_code or m.asset.serial or "" if m.asset else "")}" data-holder="{escape(m.person.full_name if m.person else "")}" '
                f'onclick="openReturnModal(this.dataset.id, this.dataset.code, this.dataset.holder)" style="font-size: 11.5px;">'
                f'<i class="fa-solid fa-arrow-rotate-left me-1"></i>{translate("Thu hồi", get_admin_lang())}</button>'
            )
            if not m.returned_at
            else Markup('<span class="text-muted small">-</span>')
        ),
    }

    column_formatters_detail = {
        "status_badge": lambda m, a: (
            Markup(f'<span class="badge bg-secondary text-white"><i class="fa-solid fa-ban me-1"></i>{translate("Đã thu hồi", get_admin_lang())}</span>')
            if m.returned_at
            else Markup(f'<span class="badge bg-success text-white"><i class="fa-solid fa-circle-check me-1"></i>{translate("Đang sử dụng", get_admin_lang())}</span>')
        ),
    }

    def list_query(self, request: Request) -> Select:
        stmt = super().list_query(request)
        return stmt.options(
            selectinload(Assignment.asset),
            selectinload(Assignment.person),
        )

    async def get_object_for_details(self, value: Any) -> Any:
        stmt = self._stmt_by_identifier(value)
        stmt = stmt.options(
            selectinload(Assignment.asset),
            selectinload(Assignment.person),
        )
        for relation in self._details_relations:
            stmt = stmt.options(selectinload(relation))
        return await self._get_object_by_pk(stmt)

    async def on_model_change(
        self, data: dict, model: Any, is_created: bool, request: Request
    ) -> None:
        await super().on_model_change(data, model, is_created, request)
        lang = request.session.get("lang", "vi")
        is_en = (lang == "en")
        is_ja = (lang == "ja")

        asset_val = data.get("asset")
        aid = getattr(asset_val, "id", None)
        if aid is None and str(asset_val).isdigit():
            aid = int(asset_val)
        if aid is None and hasattr(model, "asset_id"):
            aid = model.asset_id

        b_at = data.get("borrowed_at") or getattr(model, "borrowed_at", None)
        r_at = data.get("returned_at") if "returned_at" in data else getattr(model, "returned_at", None)

        today = dt.date.today()
        if b_at and b_at > today:
            if is_ja:
                raise ValueError(f"貸出日（{b_at}）に未来の日付を指定することはできません（本日は {today}）。")
            elif is_en:
                raise ValueError(f"Borrow date ({b_at}) cannot be in the future (today is {today}).")
            else:
                raise ValueError(f"Ngày cấp phát ({b_at.strftime('%d/%m/%Y')}) không được ở tương lai (hôm nay là {today.strftime('%d/%m/%Y')}).")

        if r_at and r_at > today:
            if is_ja:
                raise ValueError(f"返却日（{r_at}）に未来の日付を指定することはできません（本日は {today}）。")
            elif is_en:
                raise ValueError(f"Return date ({r_at}) cannot be in the future (today is {today}).")
            else:
                raise ValueError(f"Ngày thu hồi ({r_at.strftime('%d/%m/%Y')}) không được ở tương lai (hôm nay là {today.strftime('%d/%m/%Y')}).")

        if b_at and r_at and r_at < b_at:
            if is_ja:
                raise ValueError("返却日を貸出日より前にすることはできません。")
            elif is_en:
                raise ValueError("Return date cannot be before borrow date.")
            else:
                raise ValueError("Ngày thu hồi thiết bị không được trước ngày cấp phát.")

        if aid and b_at:
            current_id = getattr(model, "id", None) if not is_created else None
            with _get_admin_db(request) as db:
                query = (
                    select(Assignment)
                    .options(selectinload(Assignment.person))
                    .where(
                        Assignment.asset_id == aid,
                        Assignment.is_deleted.is_(False),
                    )
                )
                if current_id:
                    query = query.where(Assignment.id != current_id)
                existing = db.scalars(query).all()

                for other in existing:
                    o_start = other.borrowed_at
                    o_end = other.returned_at
                    holder = other.person.full_name if other.person else "nhân viên khác"

                    if o_end is None:
                        if r_at is None:
                            if is_ja:
                                raise ValueError(f"この機器は現在 '{holder}' が使用中です（未返却）。新しい割当を登録する前に前回の返却日を入力してください。")
                            elif is_en:
                                raise ValueError(f"This asset is currently in use by '{holder}'. Please record return date first.")
                            else:
                                raise ValueError(f"Thiết bị này hiện đang được bàn giao cho '{holder}' (chưa thu hồi). Vui lòng ghi nhận Ngày thu hồi trước khi tạo lượt bàn giao mới.")
                        if b_at >= o_start or r_at > o_start:
                            if is_ja:
                                raise ValueError(f"割当期間の重複: この機器は {o_start} から '{holder}' が使用中です。")
                            elif is_en:
                                raise ValueError(f"Overlapping asset assignment period: This asset is in use by '{holder}' since {o_start}.")
                            else:
                                raise ValueError(f"Trùng lặp thời gian cấp phát: Thiết bị này đang được bàn giao cho '{holder}' từ ngày {o_start.strftime('%d/%m/%Y')} (chưa thu hồi). Thời gian cấp phát mới không thể trùng lấn với người đang sử dụng.")
                    else:
                        if b_at < o_end and (r_at is None or r_at > o_start):
                            if is_ja:
                                raise ValueError(
                                    f"割当期間の重複: この機器はすでに {o_start} から {o_end} まで '{holder}' に割り当てられています。"
                                    f"入力された期間（{b_at} - {r_at or '未返却'}）は前回の割当と重複しています。"
                                )
                            elif is_en:
                                raise ValueError(
                                    f"Overlapping asset assignment period: This asset was assigned to '{holder}' from {o_start} to {o_end}. "
                                    f"The new period ({b_at} - {r_at or 'open'}) overlaps with the previous assignment."
                                )
                            else:
                                raise ValueError(
                                    f"Trùng lặp thời gian cấp phát: Thiết bị này đã được bàn giao cho '{holder}' "
                                    f"từ ngày {o_start.strftime('%d/%m/%Y')} đến ngày {o_end.strftime('%d/%m/%Y')}. "
                                    f"Thời gian cấp phát ({b_at.strftime('%d/%m/%Y')} - {r_at.strftime('%d/%m/%Y') if r_at else 'chưa thu hồi'}) "
                                    f"bị trùng lấn với lượt bàn giao trước."
                                )


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
    module = Module.LICENSES
    name = "Sản phẩm License"
    name_plural = "Danh mục Phần mềm"
    icon = "fa-solid fa-compact-disc"
    category = "License"
    column_list = [LicenseProduct.id, LicenseProduct.name, LicenseProduct.vendor]
    column_details_list = [
        LicenseProduct.id,
        LicenseProduct.name,
        LicenseProduct.vendor,
        LicenseProduct.license_type,
    ] + COMMON_EXCLUDED_COLUMNS
    column_labels = {
        "name": "Tên phần mềm",
        "vendor": "Hãng phát triển / Nhà cung cấp",
        "license_type": "Loại bản quyền",
    }


class LicenseAdmin(BaseAdminView, model=License):
    module = Module.LICENSES
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
    ] + COMMON_EXCLUDED_COLUMNS
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
                f'<span class="badge bg-danger text-white fs-6 px-2 py-1"><i class="fa-solid fa-triangle-exclamation me-1"></i>{m.remaining_seats} ({translate("Vượt định mức", get_admin_lang())})</span>'
            )
            if m.remaining_seats < 0
            else Markup(
                f'<span class="badge bg-secondary text-white fs-6 px-2 py-1">0 ({translate("Hết chỗ", get_admin_lang())})</span>'
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
                f'<span class="badge bg-danger text-white fs-6 px-2 py-1"><i class="fa-solid fa-triangle-exclamation me-1"></i>{m.remaining_seats} ({translate("Vượt định mức", get_admin_lang())})</span>'
            )
            if m.remaining_seats < 0
            else Markup(
                f'<span class="badge bg-secondary text-white fs-6 px-2 py-1">0 ({translate("Hết chỗ", get_admin_lang())})</span>'
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
    module = Module.LICENSES
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
        "status_badge",
        LicenseAssignment.assigned_at,
        LicenseAssignment.expiry_date,
        LicenseAssignment.removed_at,
    ]
    column_details_list = [
        LicenseAssignment.id,
        LicenseAssignment.license,
        LicenseAssignment.asset,
        LicenseAssignment.person,
        "status_badge",
        LicenseAssignment.assigned_at,
        LicenseAssignment.expiry_date,
        LicenseAssignment.removed_at,
        LicenseAssignment.note,
    ] + ["created_at", "created_by", "updated_at", "updated_by"]
    column_labels = {
        "license": "Bản quyền phần mềm",
        "asset": "Thiết bị được gán",
        "person": "Nhân viên được gán",
        "status_badge": "Trạng thái",
        "assigned_at": "Thời điểm gán",
        "expiry_date": "Ngày hết hạn",
        "removed_at": "Thời điểm thu hồi",
        "note": "Ghi chú",
    }
    column_formatters = {
        "license": lambda m, a: (
            Markup(
                f'<a href="/admin/license/details/{m.license_id}" class="text-decoration-none fw-bold text-primary">'
                f'<i class="fa-solid fa-compact-disc me-1"></i>{escape(m.license.product.name) if m.license and m.license.product else (escape(str(m.license)) if m.license else "-")}</a> '
                f'<span class="badge bg-light text-secondary border ms-1">{m.license.seats if m.license else ""} seats</span>'
            )
            if m.license
            else "-"
        ),
        "status_badge": lambda m, a: (
            Markup('<span class="badge bg-secondary text-white"><i class="fa-solid fa-ban me-1"></i>Đã thu hồi</span>')
            if m.removed_at
            else Markup('<span class="badge bg-success text-white"><i class="fa-solid fa-circle-check me-1"></i>Đang sử dụng</span>')
        ),
    }
    column_formatters_detail = {
        "license": lambda m, a: (
            f"{m.license.product.name} ({m.license.seats} seats)"
            if (m.license and m.license.product)
            else (str(m.license) if m.license else "-")
        ),
        "status_badge": lambda m, a: (
            Markup('<span class="badge bg-secondary text-white"><i class="fa-solid fa-ban me-1"></i>Đã thu hồi</span>')
            if m.removed_at
            else Markup('<span class="badge bg-success text-white"><i class="fa-solid fa-circle-check me-1"></i>Đang sử dụng</span>')
        ),
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
            selectinload(LicenseAssignment.license).selectinload(License.product),
            selectinload(LicenseAssignment.asset),
            selectinload(LicenseAssignment.person),
        )

    async def get_object_for_details(self, value: Any) -> Any:
        stmt = self._stmt_by_identifier(value)
        stmt = stmt.options(
            selectinload(LicenseAssignment.license).selectinload(License.product),
            selectinload(LicenseAssignment.asset),
            selectinload(LicenseAssignment.person),
        )
        for relation in self._details_relations:
            stmt = stmt.options(selectinload(relation))
        return await self._get_object_by_pk(stmt)

    async def on_model_change(
        self, data: dict, model: Any, is_created: bool, request: Request
    ) -> None:
        await super().on_model_change(data, model, is_created, request)
        lang = request.session.get("lang", "vi")
        is_en = (lang == "en")
        is_ja = (lang == "ja")

        asset_val = data.get("asset")
        person_val = data.get("person")
        if not asset_val and not person_val:
            if is_ja:
                raise ValueError("ライセンスは機器または社員に割り当てる必要があります。")
            elif is_en:
                raise ValueError("License must be assigned to an asset or person.")
            else:
                raise ValueError("Bản quyền phải được gán cho thiết bị hoặc nhân viên.")

        lic_val = data.get("license")
        lid = getattr(lic_val, "id", None)
        if lid is None and str(lic_val).isdigit():
            lid = int(lic_val)
        if lid is None and hasattr(model, "license_id"):
            lid = model.license_id

        r_at = data.get("removed_at") if "removed_at" in data else getattr(model, "removed_at", None)

        if lid and is_created and r_at is None:
            with _get_admin_db(request) as db:
                lic = db.get(License, lid)
                if lic and not lic.is_deleted:
                    active_count = db.scalar(
                        select(func.count(LicenseAssignment.id)).where(
                            LicenseAssignment.license_id == lid,
                            LicenseAssignment.removed_at.is_(None),
                            LicenseAssignment.is_deleted.is_(False),
                        )
                    ) or 0
                    if active_count >= lic.seats:
                        if is_ja:
                            raise ValueError(f"ライセンス '{lic}' の上限（{lic.seats} seats）に達しました。")
                        elif is_en:
                            raise ValueError(f"License '{lic}' has reached maximum seats ({lic.seats}).")
                        else:
                            raise ValueError(f"Bản quyền '{lic}' đã hết lượt gán (tổng {lic.seats} seats).")


class AccessCardAdmin(BaseAdminView, model=AccessCard):
    module = Module.CARDS
    name = "Thẻ ra vào"
    name_plural = "Danh sách Thẻ từ"
    icon = "fa-solid fa-address-card"
    category = "Thẻ ra vào"
    column_list = [
        AccessCard.id,
        AccessCard.card_no,
        AccessCard.card_type,
        "status_badge",
        "current_borrower",
        AccessCard.note,
    ]
    column_details_list = [
        AccessCard.id,
        AccessCard.card_no,
        AccessCard.card_type,
        AccessCard.status,
        "current_borrower",
        AccessCard.note,
    ] + COMMON_EXCLUDED_COLUMNS
    column_labels = {
        "current_borrower": "Người đang giữ thẻ",
        "card_no": "Số thẻ",
        "card_type": "Loại thẻ",
        "status_badge": "Trạng thái",
        "note": "Ghi chú",
    }
    column_formatters = {
        "status_badge": lambda m, a: (
            Markup(f'<span class="badge bg-success-subtle text-success border border-success-subtle px-2 py-1"><i class="fa-solid fa-box-archive me-1"></i>{translate("Trong kho", get_admin_lang())}</span>')
            if m.status == CardStatus.IN_STOCK
            else (
                Markup(f'<span class="badge bg-primary-subtle text-primary border border-primary-subtle px-2 py-1"><i class="fa-solid fa-user-check me-1"></i>{translate("Đang cho mượn", get_admin_lang())}</span>')
                if m.status == CardStatus.BORROWED
                else (
                    Markup(f'<span class="badge bg-danger text-white px-2 py-1"><i class="fa-solid fa-triangle-exclamation me-1"></i>{translate("Bị mất", get_admin_lang())}</span>')
                    if m.status == CardStatus.LOST
                    else Markup(f'<span class="badge bg-secondary text-white px-2 py-1">{translate("Đã hủy", get_admin_lang())}</span>')
                )
            )
        ),
        "current_borrower": lambda m, a: m.current_borrower or "-",
    }
    column_formatters_detail = {
        "status": lambda m, a: (
            Markup(f'<span class="badge bg-success-subtle text-success border border-success-subtle px-2 py-1"><i class="fa-solid fa-box-archive me-1"></i>{translate("Trong kho", get_admin_lang())} (IN_STOCK)</span>')
            if m.status == CardStatus.IN_STOCK
            else (
                Markup(f'<span class="badge bg-primary-subtle text-primary border border-primary-subtle px-2 py-1"><i class="fa-solid fa-user-check me-1"></i>{translate("Đang cho mượn", get_admin_lang())} (BORROWED)</span>')
                if m.status == CardStatus.BORROWED
                else (
                    Markup(f'<span class="badge bg-danger text-white px-2 py-1"><i class="fa-solid fa-triangle-exclamation me-1"></i>{translate("Bị mất", get_admin_lang())} (LOST)</span>')
                    if m.status == CardStatus.LOST
                    else Markup(f'<span class="badge bg-secondary text-white px-2 py-1">{translate("Đã hủy", get_admin_lang())} (DECOMMISSIONED)</span>')
                )
            )
        ),
        "current_borrower": lambda m, a: (
            Markup(f'<span class="fw-semibold text-dark"><i class="fa-solid fa-user me-1 text-primary"></i>{escape(m.current_borrower)}</span>')
            if m.current_borrower
            else Markup(f'<span class="text-muted fst-italic">- ({translate("Trong kho", get_admin_lang())})</span>')
        ),
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
    module = Module.CARDS
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
        "status_badge",
        CardLoan.borrowed_at,
        CardLoan.returned_at,
    ]
    column_details_list = [
        CardLoan.id,
        CardLoan.card,
        CardLoan.person,
        CardLoan.external_name,
        CardLoan.external_company,
        "status_badge",
        CardLoan.borrowed_at,
        CardLoan.expected_return_at,
        CardLoan.returned_at,
        CardLoan.purpose,
    ] + ["created_at", "created_by", "updated_at", "updated_by"]
    column_labels = {
        "card": "Thẻ mượn",
        "person": "Nhân viên mượn",
        "external_name": "Người mượn ngoài",
        "external_company": "Đơn vị mượn ngoài",
        "status_badge": "Trạng thái",
        "purpose": "Mục đích mượn",
        "borrowed_at": "Thời điểm mượn",
        "expected_return_at": "Dự kiến ngày trả",
        "returned_at": "Thời điểm trả",
    }
    column_formatters = {
        "status_badge": lambda m, a: (
            Markup(f'<span class="badge bg-secondary text-white"><i class="fa-solid fa-arrow-rotate-left me-1"></i>{translate("Đã trả", get_admin_lang())}</span>')
            if m.returned_at
            else Markup(f'<span class="badge bg-success text-white"><i class="fa-solid fa-id-badge me-1"></i>{translate("Đang mượn", get_admin_lang())}</span>')
        ),
    }
    column_formatters_detail = {
        "status_badge": lambda m, a: (
            Markup(f'<span class="badge bg-secondary text-white"><i class="fa-solid fa-arrow-rotate-left me-1"></i>{translate("Đã trả", get_admin_lang())}</span>')
            if m.returned_at
            else Markup(f'<span class="badge bg-success text-white"><i class="fa-solid fa-id-badge me-1"></i>{translate("Đang mượn", get_admin_lang())}</span>')
        ),
    }

    def list_query(self, request: Request) -> Select:
        stmt = super().list_query(request)
        return stmt.options(
            selectinload(CardLoan.card),
            selectinload(CardLoan.person),
        )

    async def get_object_for_details(self, value: Any) -> Any:
        stmt = self._stmt_by_identifier(value)
        stmt = stmt.options(
            selectinload(CardLoan.card),
            selectinload(CardLoan.person),
        )
        for relation in self._details_relations:
            stmt = stmt.options(selectinload(relation))
        return await self._get_object_by_pk(stmt)

    async def on_model_change(
        self, data: dict, model: Any, is_created: bool, request: Request
    ) -> None:
        await super().on_model_change(data, model, is_created, request)
        lang = request.session.get("lang", "vi")
        is_en = (lang == "en")
        is_ja = (lang == "ja")

        card_val = data.get("card")
        cid = getattr(card_val, "id", None)
        if cid is None and str(card_val).isdigit():
            cid = int(card_val)
        if cid is None and hasattr(model, "card_id"):
            cid = model.card_id

        if cid and is_created and data.get("returned_at") is None:
            with _get_admin_db(request) as db:
                card = db.get(AccessCard, cid)
                if card and card.status in (CardStatus.LOST, CardStatus.DAMAGED):
                    raise ValueError(
                        f"Thẻ '{card.card_no}' đang ở trạng thái {card.status.value}, không thể cho mượn."
                        if not is_en else f"Card '{card.card_no}' is in status {card.status.value}, cannot loan out."
                    )

        b_at = data.get("borrowed_at") or getattr(model, "borrowed_at", None)
        r_at = data.get("returned_at") if "returned_at" in data else getattr(model, "returned_at", None)

        if b_at and r_at and r_at < b_at:
            if is_ja:
                raise ValueError("返却日を貸出日より前にすることはできません。")
            elif is_en:
                raise ValueError("Return date cannot be before borrow date.")
            else:
                raise ValueError("Ngày trả thẻ không được trước ngày mượn.")

        if cid and b_at:
            current_id = getattr(model, "id", None) if not is_created else None
            with _get_admin_db(request) as db:
                query = (
                    select(CardLoan)
                    .options(selectinload(CardLoan.person))
                    .where(
                        CardLoan.card_id == cid,
                        CardLoan.is_deleted.is_(False),
                    )
                )
                if current_id:
                    query = query.where(CardLoan.id != current_id)
                existing = db.scalars(query).all()

                for other in existing:
                    o_start = other.borrowed_at
                    o_end = other.returned_at
                    borrower = other.person.full_name if other.person else (other.external_name or "người khác")

                    if o_end is None:
                        if r_at is None:
                            if is_ja:
                                raise ValueError(f"このカードは現在 '{borrower}' が借用中です（未返却）。新しい貸出を登録する前に前回の返却日を入力してください。")
                            elif is_en:
                                raise ValueError(f"This card is currently borrowed by '{borrower}' and has not been returned. Please record return date first.")
                            else:
                                raise ValueError(f"Thẻ này hiện đang được mượn bởi '{borrower}' (chưa trả). Vui lòng ghi nhận Ngày trả trước khi tạo lượt mượn mới.")
                        if b_at >= o_start or r_at > o_start:
                            if is_ja:
                                raise ValueError(f"貸出期間の重複: このカードは {o_start} から '{borrower}' が借用中です。")
                            elif is_en:
                                raise ValueError(f"Overlapping card loan period: This card is currently borrowed by '{borrower}' since {o_start}.")
                            else:
                                raise ValueError(f"Trùng lặp thời gian mượn thẻ: Thẻ này đang được mượn bởi '{borrower}' từ ngày {o_start.strftime('%d/%m/%Y')} (chưa trả). Thời gian mượn thẻ mới không thể trùng lấn với người đang giữ thẻ.")
                    else:
                        if b_at < o_end and (r_at is None or r_at > o_start):
                            if is_ja:
                                raise ValueError(
                                    f"貸出期間の重複: このカードはすでに {o_start} から {o_end} まで '{borrower}' に貸出されています。"
                                    f"入力された期間（{b_at} - {r_at or '未返却'}）は前回の貸出と重複しています。"
                                )
                            elif is_en:
                                raise ValueError(
                                    f"Overlapping card loan period: This card was borrowed by '{borrower}' from {o_start} to {o_end}. "
                                    f"The new period ({b_at} - {r_at or 'open'}) overlaps with the previous loan."
                                )
                            else:
                                raise ValueError(
                                    f"Trùng lặp thời gian mượn thẻ: Thẻ này đã được mượn bởi '{borrower}' "
                                    f"từ ngày {o_start.strftime('%d/%m/%Y')} đến ngày {o_end.strftime('%d/%m/%Y')}. "
                                    f"Thời gian mượn mới ({b_at.strftime('%d/%m/%Y')} - {r_at.strftime('%d/%m/%Y') if r_at else 'chưa trả'}) "
                                    f"bị trùng lấn với lượt mượn trước."
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
    module = Module.CONTRACTS
    name = "Hợp đồng"
    name_plural = "Hợp đồng Mua sắm IT"
    icon = "fa-solid fa-file-contract"
    category = "Hợp đồng"
    column_list = [Contract.id, Contract.code, Contract.vendor_name, Contract.signed_date, Contract.delivery_status]
    column_details_list = [
        Contract.id,
        Contract.code,
        Contract.vendor_name,
        Contract.signed_date,
        Contract.delivery_status,
        Contract.note,
    ] + COMMON_EXCLUDED_COLUMNS
    column_labels = {
        "code": "Số hợp đồng",
        "vendor_name": "Nhà cung cấp",
        "signed_date": "Ngày ký hợp đồng",
        "delivery_status": "Tiến độ giao hàng",
        "note": "Ghi chú",
    }
    form_excluded_columns = COMMON_EXCLUDED_COLUMNS + ["lines"]

    def list_query(self, request: Request) -> Select:
        stmt = super().list_query(request)
        return stmt.options(
            selectinload(Contract.lines).selectinload(ContractLine.assets),
        )


class ContractLineAdmin(BaseAdminView, model=ContractLine):
    module = Module.CONTRACTS
    name = "Hạng mục Hợp đồng"
    name_plural = "Chi tiết Hạng mục"
    icon = "fa-solid fa-list-check"
    category = "Hợp đồng"
    column_list = [
        ContractLine.id,
        ContractLine.contract,
        ContractLine.item_type,
        ContractLine.qty_ordered,
        "qty_delivered",
        "qty_remaining",
        "delivery_progress",
    ]
    column_details_list = [
        ContractLine.id,
        ContractLine.contract,
        ContractLine.item_type,
        ContractLine.spec,
        ContractLine.qty_ordered,
        "qty_delivered",
        "qty_remaining",
        "delivery_progress",
    ] + COMMON_EXCLUDED_COLUMNS
    column_labels = {
        "contract": "Hợp đồng",
        "item_type": "Hạng mục hàng hóa",
        "spec": "Thông số kỹ thuật",
        "qty_ordered": "Số lượng đặt mua",
        "qty_delivered": "Đã nhận",
        "qty_remaining": "Còn lại",
        "delivery_progress": "Tiến độ",
    }
    column_formatters = {
        "qty_delivered": lambda m, a: Markup(
            f'<span class="badge bg-primary text-white fs-6 px-2 py-1"><i class="fa-solid fa-box-open me-1"></i>{m.qty_delivered}</span>'
        ),
        "qty_remaining": lambda m, a: Markup(
            f'<span class="badge bg-secondary text-white fs-6 px-2 py-1">{m.qty_remaining}</span>'
        ),
        "delivery_progress": lambda m, a: (
            Markup(
                f'<span class="badge bg-success text-white"><i class="fa-solid fa-circle-check me-1"></i>{translate("Đã đủ hàng", get_admin_lang())}</span>'
            )
            if m.qty_delivered >= m.qty_ordered
            else (
                Markup(
                    f'<span class="badge bg-warning text-dark me-2"><i class="fa-solid fa-clock me-1"></i>{translate("Giao một phần", get_admin_lang())} ({m.qty_delivered}/{m.qty_ordered})</span>'
                    f'<a href="/admin/contract-line/{m.id}/receive" class="btn btn-sm btn-outline-primary py-0 px-2 fw-semibold" style="font-size: 11px;"><i class="fa-solid fa-boxes-packing me-1"></i>{translate("Nhận hàng", get_admin_lang())}</a>'
                )
                if m.qty_delivered > 0
                else Markup(
                    f'<span class="badge bg-light text-secondary border me-2"><i class="fa-regular fa-clock me-1"></i>{translate("Chưa nhận", get_admin_lang())}</span>'
                    f'<a href="/admin/contract-line/{m.id}/receive" class="btn btn-sm btn-outline-primary py-0 px-2 fw-semibold" style="font-size: 11px;"><i class="fa-solid fa-boxes-packing me-1"></i>{translate("Nhận hàng", get_admin_lang())}</a>'
                )
            )
        ),
    }
    column_formatters_detail = {
        "qty_delivered": lambda m, a: Markup(
            f'<span class="badge bg-primary text-white fs-6 px-2 py-1"><i class="fa-solid fa-box-open me-1"></i>{m.qty_delivered}</span>'
        ),
        "qty_remaining": lambda m, a: Markup(
            f'<span class="badge bg-secondary text-white fs-6 px-2 py-1">{m.qty_remaining}</span>'
        ),
        "delivery_progress": lambda m, a: (
            Markup(
                f'<span class="badge bg-success text-white"><i class="fa-solid fa-circle-check me-1"></i>{translate("Đã đủ hàng", get_admin_lang())}</span>'
            )
            if m.qty_delivered >= m.qty_ordered
            else (
                Markup(
                    f'<span class="badge bg-warning text-dark me-2"><i class="fa-solid fa-clock me-1"></i>{translate("Giao một phần", get_admin_lang())} ({m.qty_delivered}/{m.qty_ordered})</span>'
                    f'<a href="/admin/contract-line/{m.id}/receive" class="btn btn-sm btn-primary text-white py-0 px-2 fw-semibold" style="font-size: 12px;"><i class="fa-solid fa-boxes-packing me-1"></i>{translate("Nhập kho theo lô", get_admin_lang())}</a>'
                )
                if m.qty_delivered > 0
                else Markup(
                    f'<span class="badge bg-light text-secondary border me-2"><i class="fa-regular fa-clock me-1"></i>{translate("Chưa nhận", get_admin_lang())}</span>'
                    f'<a href="/admin/contract-line/{m.id}/receive" class="btn btn-sm btn-primary text-white py-0 px-2 fw-semibold" style="font-size: 12px;"><i class="fa-solid fa-boxes-packing me-1"></i>{translate("Nhập kho theo lô", get_admin_lang())}</a>'
                )
            )
        ),
    }
    form_excluded_columns = COMMON_EXCLUDED_COLUMNS + ["assets"]

    def list_query(self, request: Request) -> Select:
        stmt = super().list_query(request)
        return stmt.options(
            selectinload(ContractLine.contract),
            selectinload(ContractLine.assets),
        )

    async def get_object_for_details(self, value: Any) -> Any:
        stmt = self._stmt_by_identifier(value)
        stmt = stmt.options(
            selectinload(ContractLine.contract),
            selectinload(ContractLine.assets),
        )
        for relation in self._details_relations:
            stmt = stmt.options(selectinload(relation))
        return await self._get_object_by_pk(stmt)



class PhoneAdmin(BaseAdminView, model=Phone):
    module = Module.PHONES
    name = "Thiết bị Thoại"
    name_plural = "Danh bạ & Thiết bị Điện thoại"
    icon = "fa-solid fa-phone"
    category = "Danh bạ thoại"
    column_list = [Phone.id, Phone.extension_number, Phone.device_name, Phone.device_type, Phone.location, Phone.is_active]
    column_details_list = [
        Phone.id,
        Phone.extension_number,
        Phone.device_name,
        Phone.device_type,
        Phone.location,
        Phone.is_active,
        Phone.remarks,
    ] + COMMON_EXCLUDED_COLUMNS
    column_labels = {
        "device_name": "Tên máy điện thoại",
        "device_type": "Loại điện thoại",
        "extension_number": "Số máy nhánh (Ext)",
        "location": "Vị trí đặt",
        "is_active": "Trạng thái hoạt động",
        "remarks": "Ghi chú",
    }


class AuditLogAdmin(BaseAdminView, model=AuditLog):
    module = Module.AUDIT
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

_admin_instance: TokuyamaAdmin | None = None


def get_admin() -> TokuyamaAdmin | None:
    """Trả về instance của TokuyamaAdmin đã khởi tạo."""
    return _admin_instance


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

        if request.method == "GET":
            # Nếu đã có phiên đăng nhập hợp lệ: chuyển hướng ngay đến trang tổng quan
            token = request.session.get("token") or request.cookies.get("itam_session")
            if token:
                payload = verify_session_token(token)
                if payload:
                    return RedirectResponse(request.url_for("admin:index"), status_code=302)
            return await self.templates.TemplateResponse(request, "sqladmin/login.html")

        ok = await self.authentication_backend.login(request)
        if not ok:
            context = {
                "error": getattr(
                    request.state, "login_error", "Tên đăng nhập hoặc mật khẩu không chính xác."
                )
            }
            return await self.templates.TemplateResponse(
                request, "sqladmin/login.html", context, status_code=400
            )

        redirect_url = getattr(request.state, "redirect_url", None) or request.url_for("admin:index")
        response = RedirectResponse(redirect_url, status_code=302)
        sess_token = request.session.get("token")
        if sess_token:
            response.set_cookie(
                key="itam_session",
                value=sess_token,
                httponly=True,
                samesite="lax",
                secure=(request.url.scheme == "https"),
                max_age=1800,
            )
        return response

    async def logout(self, request: Request) -> Response:
        """Đăng xuất hoàn toàn: thu hồi token reveal, xoá session, xoá cookies và điều hướng về trang đăng nhập."""
        token = request.session.get("token") or request.cookies.get("itam_session")
        if token:
            payload = verify_session_token(token)
            if payload and "user_id" in payload:
                try:
                    from app.routers.auth import reveal_gate
                    reveal_gate.revoke(payload["user_id"])
                except Exception:
                    pass

        if self.authentication_backend:
            await self.authentication_backend.logout(request)

        if hasattr(request, "session"):
            request.session.clear()

        response = RedirectResponse(request.url_for("admin:login"), status_code=302)
        response.delete_cookie("itam_session", path="/")
        response.delete_cookie("admin_session", path="/")
        return response

    @login_required
    async def index(self, request: Request) -> Response:
        """Dashboard tổng quan hệ thống ITAM Tokuyama theo triết lý Swiss."""
        from app.core.i18n import get_current_lang, translate

        current_lang = get_current_lang(request)
        today = dt.date.today()
        sixty_days_later = today + dt.timedelta(days=60)
        user_role = request.session.get("role") or RoleCode.ADMIN.value
        can_view_audit = (user_role in (RoleCode.ADMIN.value, RoleCode.EXECUTIVE.value))
        can_view_licenses = (user_role in (RoleCode.ADMIN.value, RoleCode.EXECUTIVE.value))

        with SessionLocal() as db:
            counts_stmt = select(
                select(func.count()).select_from(Asset).where(Asset.is_deleted.is_(False)).scalar_subquery(),
                select(func.count()).select_from(Assignment).where(Assignment.returned_at.is_(None)).scalar_subquery(),
                select(func.count()).select_from(License).where(License.is_deleted.is_(False)).scalar_subquery(),
                select(func.count()).select_from(AccessCard).where(AccessCard.is_deleted.is_(False)).scalar_subquery(),
                select(func.count()).select_from(Person).where(Person.is_deleted.is_(False)).scalar_subquery(),
                select(func.count()).select_from(Contract).where(Contract.is_deleted.is_(False)).scalar_subquery(),
                select(func.count()).select_from(CardLoan).where(CardLoan.returned_at.is_(None)).scalar_subquery(),
            )
            counts_row = db.execute(counts_stmt).first()
            if counts_row:
                (
                    asset_count,
                    assignment_count,
                    license_count,
                    card_count,
                    person_count,
                    contract_count,
                    active_card_loans,
                ) = counts_row
            else:
                asset_count = assignment_count = license_count = card_count = person_count = contract_count = active_card_loans = 0

            # Audit logs (chỉ query khi có quyền xem)
            recent_logs = []
            if can_view_audit:
                recent_logs = db.scalars(
                    select(AuditLog).options(joinedload(AuditLog.user)).order_by(AuditLog.id.desc()).limit(8)
                ).all()

            # Overdue card loans (FR-17) - hiển thị cho cả Admin, GA Manager, Executive
            overdue_loans_raw = db.scalars(
                select(CardLoan)
                .options(
                    joinedload(CardLoan.card),
                    joinedload(CardLoan.person),
                )
                .where(
                    CardLoan.returned_at.is_(None),
                    CardLoan.expected_return_at.is_not(None),
                    CardLoan.expected_return_at < today,
                )
                .order_by(CardLoan.expected_return_at.asc())
                .limit(8)
            ).all()

            overdue_card_loans = []
            for loan in overdue_loans_raw:
                days_overdue = (today - loan.expected_return_at).days if loan.expected_return_at else 0
                borrower = loan.person.full_name if loan.person else (loan.external_name or "N/A")
                company = f" [{loan.external_company}]" if loan.external_company else ""
                overdue_card_loans.append({
                    "id": loan.id,
                    "card_id": loan.card_id,
                    "card_number": loan.card.card_no if loan.card else f"#{loan.card_id}",
                    "borrower": f"{borrower}{company}",
                    "borrowed_at": loan.borrowed_at,
                    "expected_return_at": loan.expected_return_at,
                    "days_overdue": days_overdue,
                })

            # Expiring licenses within 60 days (FR-17) - chỉ query khi có quyền xem
            expiring_licenses = []
            if can_view_licenses:
                expiring_lics_raw = db.scalars(
                    select(License)
                    .options(
                        joinedload(License.product),
                        selectinload(License.assignments),
                    )
                    .where(
                        License.is_deleted.is_(False),
                        License.expiry_date.is_not(None),
                        License.expiry_date <= sixty_days_later,
                    )
                    .order_by(License.expiry_date.asc())
                    .limit(8)
                ).all()

                for lic in expiring_lics_raw:
                    days_left = (lic.expiry_date - today).days if lic.expiry_date else 0
                    active_assignments = len([a for a in lic.assignments if a.removed_at is None])
                    product_name = lic.product.name if lic.product else "N/A"
                    expiring_licenses.append({
                        "id": lic.id,
                        "product_name": product_name,
                        "license_type": lic.product.license_type.value if (lic.product and lic.product.license_type) else "",
                        "expiry_date": lic.expiry_date,
                        "days_left": days_left,
                        "is_expired": days_left < 0,
                        "seats_used": f"{active_assignments}/{lic.seats}",
                        "note": lic.note or "",
                    })

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
            "overdue_card_loans": overdue_card_loans,
            "expiring_licenses": expiring_licenses,
            "can_view_audit": can_view_audit,
            "can_view_licenses": can_view_licenses,
        }
        return await self.templates.TemplateResponse(request, "sqladmin/index.html", context)


def setup_admin(app, engine):
    admin = TokuyamaAdmin(
        app,
        engine,
        title="Tokuyama IT Portal",
        logo_url="/static/img/logo.png",
        favicon_url="/static/img/tokuyama-favicon.png",
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

    global _admin_instance
    _admin_instance = admin

    return admin
