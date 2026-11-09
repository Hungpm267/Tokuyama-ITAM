"""Tích hợp SQLAdmin cho hệ thống quản trị ITAM - Tokuyama Vietnam.

Quy định bảo mật GEMINI.md:
- Chỉ tài khoản có vai trò ADMIN mới được truy cập /admin.
- Tuyệt đối không để lộ các trường nhạy cảm trong REDACTED_FIELDS (pc_password_enc, email_password_enc, license_key_enc, password_hash).
- AuditLog là bảng bất biến: cấm tạo, sửa, xoá trên giao diện (can_create=False, can_edit=False, can_delete=False).
"""

from __future__ import annotations

import contextlib
import contextvars
import csv
import io
import datetime as dt
import logging
from pathlib import Path
from typing import Any

import anyio
from sqladmin import Admin, ModelView
from sqladmin.authentication import AuthenticationBackend, login_required
from sqladmin.forms import ModelConverter
from sqladmin.helpers import get_object_identifier
from starlette.datastructures import FormData, URL
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response, StreamingResponse
from starlette.types import ASGIApp, Receive, Scope, Send
import time
from sqlalchemy import Select, String, Text, func, or_, select
from sqlalchemy.orm import Session, joinedload, selectinload
from markupsafe import Markup, escape


from app.core.audit import audit_login, record_audit
from app.core.clock import today_local
from app.core.i18n import (
    DEFAULT_ADMIN_COLUMN_LABELS,
    format_datetime_clean,
    get_current_lang,
    get_property_label,
    translate,
)
from app.core.permissions import get_user_permissions, has_permission
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
from app.enums import (
    AssetStatus,
    AuditAction,
    Module,
    PermissionAction,
    PersonStatus,
    PersonType,
    RoleCode,
)
from app.models import (
    Asset,
    AssetCategory,
    AssetTag,
    Assignment,
    AuditLog,
    Department,
    Person,
    PersonSecret,
    REDACTED_FIELDS,
    Role,
    User,
)
from app.services import person_code_service

logger = logging.getLogger(__name__)

SYSTEM_ROLE_CODES = (RoleCode.ADMIN.value, RoleCode.GA_MANAGER.value, RoleCode.EXECUTIVE.value)

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


def _request_lang(request: Request) -> str:
    """Ngôn ngữ cho thông báo phía server - cùng nguồn với giao diện (cookie itam_lang trước).

    Đọc `session["lang"]` thì chỉ ra ngôn ngữ lúc đăng nhập: đổi sang English xong
    giao diện là tiếng Anh nhưng lỗi nhập liệu vẫn hiện tiếng Việt.
    """
    try:
        return get_current_lang(request)
    except Exception:
        return "vi"


def _column_snapshot(obj: Any) -> dict[str, Any]:
    """Giá trị các cột của một bản ghi để ghi audit (record_audit tự che cột nhạy cảm)."""
    snapshot: dict[str, Any] = {}
    for col in obj.__table__.columns:
        val = getattr(obj, col.name, None)
        if isinstance(val, (dt.datetime, dt.date)):
            val = val.isoformat()
        elif hasattr(val, "value") and not isinstance(val, (str, bytes)):
            val = val.value
        snapshot[col.name] = val
    return snapshot


#: Danh mục / vai trò không được xóa khi còn bản ghi đang dùng: (model bị xóa) -> [(model tham chiếu, cột, tên gọi)]
_IN_USE_REFERENCES: dict[Any, list[tuple[Any, str, str]]] = {}


def _in_use_references() -> dict[Any, list[tuple[Any, str, str]]]:
    if not _IN_USE_REFERENCES:
        _IN_USE_REFERENCES.update({
            Department: [(Person, "department_id", "nhân sự")],
            AssetCategory: [(Asset, "category_id", "thiết bị")],
            Role: [(User, "role_id", "tài khoản người dùng")],
        })
    return _IN_USE_REFERENCES


def _in_use_blocker(db: Session, model_cls: Any, obj: Any) -> str | None:
    """Thông báo lỗi nếu bản ghi danh mục còn được bản ghi sống khác trỏ tới.

    Xóa danh mục đang dùng làm các bản ghi đó trỏ vào thứ không còn chọn được;
    lần sửa kế tiếp sẽ buộc phải đổi sang giá trị khác.
    """
    for ref_model, column, label in _in_use_references().get(model_cls, []):
        stmt = select(func.count()).select_from(ref_model).where(getattr(ref_model, column) == obj.id)
        if hasattr(ref_model, "is_deleted"):
            stmt = stmt.where(ref_model.is_deleted.is_(False))
        count = db.scalar(stmt) or 0
        if count > 0:
            return f"Không thể xóa vì đang có {count} {label} sử dụng bản ghi này. Hãy chuyển chúng sang giá trị khác trước."
    return None


def user_can(request: Request | None, module: str, action: str) -> bool:
    """Người dùng của request có quyền (module, action) không - dùng cho template và formatter.

    Nút thao tác phải theo đúng ma trận quyền (kể cả quyền ghi đè), cùng phép kiểm tra mà
    endpoint dùng. Kiểm theo tên vai trò thì có nút bấm vào luôn 403, và có quyền được cấp
    mà không bao giờ thấy nút.
    """
    if request is None:
        return False
    cache = getattr(request.state, "itam_can_cache", None)
    if cache is None:
        cache = {}
        request.state.itam_can_cache = cache
    key = (module, action)
    if key not in cache:
        try:
            with SessionLocal() as db:
                user = get_user_from_request(request, db)
                cache[key] = bool(user) and has_permission(db, user, Module(module), PermissionAction(action))
        except Exception:
            cache[key] = False
    return cache[key]


def user_can_loan(request: Request | None) -> bool:
    """Cùng điều kiện với endpoint bàn giao / thu hồi (app/routers/assets.py)."""
    return any(
        user_can(request, module, action)
        for module in ("assets", "assignments")
        for action in ("change", "add")
    )




def _csv_safe(value: Any) -> str:
    """Giá trị văn bản an toàn cho Excel: ô bắt đầu bằng = + - @ sẽ bị chạy như công thức."""
    text_val = "" if value is None else str(value)
    if text_val and text_val[0] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + text_val
    return text_val


#: Từ khóa cho thấy một "loại tài sản" thực ra là phần mềm, không phải thiết bị.
_SOFTWARE_CATEGORY_WORDS = (
    "license", "licence", "software", "phần mềm", "phan mem", "bản quyền", "ban quyen",
    "ライセンス", "ソフトウェア", "ソフト",
)


def _pk_of(value: Any) -> int | None:
    """Khoá chính từ một trường quan hệ của form SQLAdmin (gửi lên dạng chuỗi pk)."""
    if value is None or value == "":
        return None
    ident = getattr(value, "id", None)
    if ident is not None:
        return int(ident)
    text_val = str(value).strip()
    return int(text_val) if text_val.isdigit() else None


def _form_fk(data: dict, key: str, model: Any, attr: str) -> int | None:
    """Khoá ngoại SAU khi lưu: lấy từ form nếu form có gửi trường đó, ngược lại giữ giá trị hiện có."""
    if key in data:
        picked = _pk_of(data.get(key))
        if picked is not None:
            return picked
    return getattr(model, attr, None)


def _enum_of(enum_cls: Any, raw: Any) -> Any:
    """Form SQLAdmin gửi ENUM dưới dạng tên thành viên (chuỗi)."""
    if raw is None or raw == "":
        return None
    if isinstance(raw, enum_cls):
        return raw
    try:
        return enum_cls[str(raw)]
    except KeyError:
        try:
            return enum_cls(str(raw))
        except ValueError:
            return None


def _msg(lang: str, vi: str, en: str, ja: str) -> str:
    if lang == "ja":
        return ja
    if lang == "en":
        return en
    return vi


def _reject_future_date(value: dt.date | None, lang: str, vi: str, en: str, ja: str) -> None:
    today = today_local()
    if value and value > today:
        raise ValueError(
            _msg(
                lang,
                f"{vi} ({value.strftime('%d/%m/%Y')}) không được ở tương lai (hôm nay là {today.strftime('%d/%m/%Y')}).",
                f"{en} ({value}) cannot be in the future (today is {today}).",
                f"{ja}（{value}）に未来の日付を指定することはできません（本日は {today}）。",
            )
        )


def _require_active_person(db: Session, person_id: int, lang: str) -> None:
    """Người nhận máy/thẻ/bản quyền phải còn tồn tại và chưa nghỉ việc (cùng luật với tầng service)."""
    person = db.get(Person, person_id)
    if not person or person.is_deleted:
        raise ValueError(_msg(
            lang,
            "Nhân viên được chọn không tồn tại hoặc đã bị xóa.",
            "The selected employee does not exist or has been deleted.",
            "選択された社員は存在しないか、削除されています。",
        ))
    if person.status == PersonStatus.RESIGNED:
        raise ValueError(_msg(
            lang,
            f"Không thể cấp phát cho nhân viên đã nghỉ việc ({person.full_name}).",
            f"Cannot assign to a resigned employee ({person.full_name}).",
            f"退職済みの社員（{person.full_name}）には割り当てできません。",
        ))


def _sync_asset_status(db: Session, asset_id: int, user_id: Any, ip_address: str | None) -> None:
    """Đưa assets.status về khớp với việc thiết bị có lượt bàn giao đang mở hay không."""
    asset = db.get(Asset, asset_id)
    if not asset:
        return
    has_open = db.scalar(
        select(Assignment.id).where(
            Assignment.asset_id == asset.id,
            Assignment.returned_at.is_(None),
            Assignment.is_deleted.is_(False),
        ).limit(1)
    )
    old_status = asset.status
    if has_open:
        new_status = AssetStatus.IN_USE
    elif old_status == AssetStatus.IN_USE:
        new_status = AssetStatus.IN_STOCK
    else:
        return
    if new_status == old_status:
        return
    asset.status = new_status
    record_audit(
        db=db,
        action=AuditAction.UPDATE,
        table_name="assets",
        record_id=asset.id,
        user_id=user_id,
        before={"status": old_status.value},
        after={"status": new_status.value},
        ip_address=ip_address,
    )












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


_MODEL_COUNT_CACHE: dict[tuple[type, tuple], tuple[float, int]] = {}
_COUNT_CACHE_IGNORED_PARAMS = frozenset({"page", "pageSize", "sortBy", "sort", "search"})
_MODEL_COUNT_CACHE_TTL = 30.0  # 30s cache cho số lượng bản ghi để tiết kiệm roundtrip Aiven Cloud


def invalidate_model_count_cache(model: type | None = None) -> None:
    """Xóa cache số lượng bản ghi khi có thao tác thêm, xóa, sửa hoặc khôi phục."""
    if model is None:
        _MODEL_COUNT_CACHE.clear()
    else:
        for key in [k for k in _MODEL_COUNT_CACHE if k[0] is model]:
            _MODEL_COUNT_CACHE.pop(key, None)


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

            # authenticate() chỉ chấp nhận 3 vai trò hệ thống. Cho đăng nhập bằng vai trò
            # khác sẽ tạo vòng lặp /admin <-> /admin/login không thoát ra được.
            role_supported = bool(user and user.role and user.role.code in SYSTEM_ROLE_CODES)

            if user and valid_password and not role_supported:
                request.state.login_error = "Vai trò của tài khoản này chưa được cấp quyền truy cập hệ thống."
                audit_login(db, user_id=user.id, success=False, username=username, ip_address=client_ip)
                db.commit()
                return False

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

                # Sổ tổng là trang làm việc chính của cả 3 vai trò
                request.state.redirect_url = "/admin/so-tong"
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
        # Cookie itam_session được gia hạn theo thao tác (sliding); token lưu trong
        # admin_session thì không, nên phải thử cookie trước.
        payload = None
        for token in (request.cookies.get("itam_session"), request.session.get("token")):
            if token:
                payload = verify_session_token(token)
                if payload:
                    break
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
    # Cắt phần "[SQL: INSERT INTO assets (device_code, serial...)]" trước khi
    # so khớp: câu SQL liệt kê mọi cột nên trùng mã thiết bị từng bị báo thành trùng serial.
    full = str(msg)
    m = full.split("[SQL:")[0]
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
    if "expected_after_borrowed" in m:
        return _tr("Ngày dự kiến trả không được trước ngày mượn.", "Expected return date cannot be before borrow date.", "返却予定日を貸出日より前にすることはできません。")
    if "has_some_identifier" in m:
        return _tr("Tài sản phải có ít nhất một mã định danh (Mã GA, PC Name hoặc Số Serial).", "Asset must have at least one identifier (GA code, PC Name or Serial).", "資産には少なくとも1つの識別子（GAコード、PC名、またはシリアル）が必要です。")
    if "staff_code_format" in m:
        return _tr("Mã nhân viên không đúng định dạng chuẩn TVC (Ví dụ: TVC00001).", "Staff code does not match standard TVC format (e.g. TVC00001).", "社員番号の形式が正しくありません（例：TVC00001）。")
    if "smallint out of range" in m or "numericvalueoutofrange" in m.lower():
        return _tr("Giá trị số nhập vào vượt quá giới hạn cho phép.", "Numeric value is out of allowable range.", "入力された数値が許容範囲を超えています。")

    if "unique constraint" in m.lower() or "uniqueviolation" in m.lower() or "uq_" in m:
        # Kiểm tra các ràng buộc one_open_per (đang có hiệu lực chưa kết thúc)
        if "uq_open_assignments_asset_id" in m:
            return _tr(
                "Thiết bị này hiện đang được bàn giao cho nhân viên khác sử dụng (chưa thu hồi). Vui lòng cập nhật Ngày thu hồi ở lượt bàn giao trước đó trước khi bàn giao lại.",
                "This asset is currently in use and has not been returned yet. Please record the return date before reassigning.",
                "この機器は現在他の担当者に貸出中です（未返却）。再貸出する前に前回の返却日を入力してください。",
            )

        if "serial" in m:
            return _tr("Số Serial này đã tồn tại trong hệ thống (bị trùng lặp).", "Serial number already exists in system.", "このシリアル番号はすでにシステムに存在します。")
        if "device_code" in m:
            return _tr("Mã thiết bị này đã tồn tại trong hệ thống (bị trùng lặp).", "Device code already exists in system.", "この機器コードはすでにシステムに存在します。")
        if "staff_code" in m:
            return _tr("Mã nhân viên này đã tồn tại trong hệ thống (bị trùng lặp).", "Staff code already exists in system.", "この社員番号はすでにシステムに存在します。")
        if "persons_user_id" in m:
            return _tr("UserID này đã thuộc về nhân sự khác.", "UserID already belongs to another person.", "このUserIDはすでに別の社員に紐付けられています。")
        if "username" in m:
            return _tr("Tên đăng nhập này đã tồn tại trong hệ thống (bị trùng lặp).", "Username already exists in system.", "このユーザー名はすでにシステムに存在します。")
        if "email" in m:
            return _tr("Email này đã được dùng cho một nhân sự khác (bị trùng lặp).", "Email already belongs to another employee.", "このEmailはすでに別の社員に使用されています。")
        return _tr("Dữ liệu bị trùng lặp với bản ghi đã tồn tại trong hệ thống.", "Record already exists in system (duplicate).", "システム内に重複するデータが存在します。")

    if "foreign key" in m.lower() or "foreignkeyviolation" in m.lower():
        return _tr("Không thể lưu hoặc xóa vì dữ liệu đang được liên kết với bản ghi khác.", "Cannot save or delete because data is referenced elsewhere.", "他のデータから参照されているため、保存または削除できません。")
    if "not-null constraint" in m.lower() or "notnullviolation" in m.lower():
        return _tr("Vui lòng nhập đầy đủ các trường thông tin bắt buộc.", "Please fill in all required fields.", "必須項目をすべて入力してください。")

    if "(psycopg." in full or "[SQL:" in full:
        clean = m.strip()
        clean = clean.split("DETAIL:")[0].strip()
        return clean

    return full


# --- Base Model View ---

class AliveOnlyModelConverter(ModelConverter):
    """Ô chọn quan hệ trên form chỉ liệt kê bản ghi chưa xóa mềm.

    Mặc định SQLAdmin nạp lựa chọn bằng `select(target_model)` trần, nên thiết bị,
    nhân viên, loại tài sản... đã xóa vẫn hiện ra để chọn (bất biến số 5: mọi truy
    vấn trên bảng nghiệp vụ mặc định lọc is_deleted = false).

    Ngoại lệ bắt buộc: khi SỬA một bản ghi, giá trị nó ĐANG trỏ tới phải còn trong
    danh sách dù đã bị xóa mềm. Thiếu nó, trình duyệt tự chọn dòng đầu tiên và lần
    lưu kế tiếp âm thầm trỏ bản ghi (kể cả dòng lịch sử đã đóng) sang giá trị khác.
    """

    async def _prepare_select_options(self, prop: Any, session_maker: Any) -> list[tuple[str, Any]]:
        target_model = prop.mapper.class_
        if not hasattr(target_model, "is_deleted"):
            return await super()._prepare_select_options(prop, session_maker)

        condition = target_model.is_deleted.is_(False)
        current = self._currently_linked(prop)
        if current is not None:
            condition = or_(condition, current)
        stmt = select(target_model).where(condition)
        deleted_suffix = translate("đã xóa", get_admin_lang())

        def _load() -> list[tuple[str, Any]]:
            with session_maker() as session:
                rows = session.execute(stmt).scalars().unique().all()
                return [
                    (str(self._get_identifier_value(obj)), self._option_label(obj, deleted_suffix))
                    for obj in rows
                ]

        return await anyio.to_thread.run_sync(_load)

    @staticmethod
    def _option_label(obj: Any, deleted_suffix: str) -> str:
        label = str(obj)
        if obj.is_deleted:
            label = f"{label} ({deleted_suffix})"
        return label

    @staticmethod
    def _currently_linked(prop: Any) -> Any:
        """Điều kiện SQL chọn các bản ghi mà đối tượng đang được sửa hiện trỏ tới (None nếu không phải form sửa)."""
        request = current_request_ctx.get()
        if request is None or "/edit/" not in request.url.path:
            return None
        raw_pk = str(request.path_params.get("pk", "") if hasattr(request, "path_params") else "")
        if not raw_pk.isdigit() or prop.secondary is not None:
            return None
        parent_pk_cols = list(prop.parent.primary_key)
        if len(parent_pk_cols) != 1:
            return None
        parent_pk = parent_pk_cols[0]
        edited_pk = int(raw_pk)

        clauses = []
        for local_col, remote_col in prop.local_remote_pairs:
            if local_col is parent_pk:
                # một-nhiều: bản ghi con trỏ ngược về đối tượng đang sửa
                clauses.append(remote_col == edited_pk)
            else:
                # nhiều-một: khóa ngoại nằm trên chính đối tượng đang sửa
                clauses.append(remote_col.in_(select(local_col).where(parent_pk == edited_pk)))
        return or_(*clauses) if clauses else None


class BaseAdminView(ModelView):
    module: Module | None = None
    form_converter = AliveOnlyModelConverter
    #: Chỉ CSV: bản JSON của SQLAdmin không qua bước làm sạch dưới đây.
    export_types = ["csv"]
    #: Các ô văn bản phải là duy nhất KHÔNG phân biệt chữ hoa-thường ("abc123" trùng "ABC123").
    unique_text_fields: tuple[str, ...] = ()

    def get_export_columns(self) -> list[str]:
        """Xuất đúng các cột người dùng thấy trên danh sách.

        Mặc định SQLAdmin xuất mọi thuộc tính của model: cột kỹ thuật (is_deleted,
        delete_reason...), quan hệ in ra dạng `<Assignment object at 0x...>`, và không có
        các cột tính toán như người đang giữ máy.
        """
        names: list[str] = []
        for name in self._list_prop_names:
            if name in REDACTED_FIELDS:
                continue
            if name == "status_badge":
                # Cột huy hiệu chỉ là HTML; dữ liệu thật nằm ở cột `status` nếu model có.
                if hasattr(self.model, "status") and "status" not in names:
                    names.append("status")
                continue
            if not hasattr(self.model, name):
                continue  # cột nút bấm / tiến độ chỉ có trên giao diện
            names.append(name)
        return names

    async def get_model_objects(self, request: Request, limit: int | None = 0) -> list[Any]:
        """Dữ liệu xuất theo đúng ô tìm kiếm và bộ lọc đang chọn trên danh sách."""
        stmt = self.list_query(request)
        search = request.query_params.get("search")
        if search:
            stmt = self.search_query(stmt=stmt, term=search)
        stmt = stmt.limit(None if limit == 0 else limit)
        for relation in self._list_relations:
            stmt = stmt.options(selectinload(relation))
        return await self._run_query(stmt)

    async def _export_csv(self, data: list[Any]) -> StreamingResponse:
        lang = get_admin_lang()
        names = self._export_prop_names

        async def _cell(row: Any, name: str) -> str:
            value = await self.get_prop_value(row, name)
            if value is None:
                return ""
            if isinstance(value, (dt.datetime, dt.date)):
                return format_datetime_clean(value)
            if isinstance(value, bool):
                return "Yes" if value else "No"
            if isinstance(value, (int, float)):
                return str(value)
            if isinstance(value, (list, tuple, set)):
                return _csv_safe("; ".join(str(v) for v in value))
            if hasattr(value, "value") and not isinstance(value, str):
                return _csv_safe(value.value)
            return _csv_safe(value)

        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow([get_property_label(self, name, lang) for name in names])
        for row in data:
            writer.writerow([await _cell(row, name) for name in names])

        # BOM để Excel nhận đúng UTF-8 (tiếng Việt / tiếng Nhật không bị lỗi font).
        payload = ("\ufeff" + buffer.getvalue()).encode("utf-8")
        filename = f"{self.identity}_{today_local().isoformat()}.csv"
        return StreamingResponse(
            iter([payload]),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f"attachment;filename={filename}"},
        )
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
            lang = _request_lang(request)
            raise ValueError(humanize_error_str(str(e), lang=lang)) from e

    async def update_model(self, request: Request, pk: Any, data: dict) -> Any:
        try:
            res = await super().update_model(request, pk, data)
            invalidate_model_count_cache(self.model)
            return res
        except Exception as e:
            lang = _request_lang(request)
            raise ValueError(humanize_error_str(str(e), lang=lang)) from e

    async def on_model_change(
        self, data: dict, model: Any, is_created: bool, request: Request
    ) -> None:
        lang = _request_lang(request)
        is_en = (lang == "en")

        columns = self.model.__table__.columns

        # Cắt khoảng trắng đầu/cuối của mọi ô văn bản. Không làm thì "  TVC-E01 " và
        # "TVC-E01" là hai mã khác nhau, và một ô bắt buộc chỉ gõ dấu cách vẫn lưu được.
        for key, value in list(data.items()):
            if not isinstance(value, str) or key in REDACTED_FIELDS:
                continue
            stripped = value.strip()
            data[key] = stripped
            col = columns.get(key)
            if col is not None and not col.nullable and stripped == "" and isinstance(col.type, (String, Text)):
                label = getattr(self, "column_labels", {}).get(key) or key
                raise ValueError(_msg(
                    lang,
                    f"Vui lòng nhập '{label}' (không được để trống hoặc chỉ gồm khoảng trắng).",
                    f"'{label}' is required and cannot be blank.",
                    f"「{label}」は必須です（空白のみは不可）。",
                ))

        # Trùng mã không phân biệt chữ hoa-thường. Chỉ số duy nhất của DB phân biệt hoa-thường,
        # nên "abc123" và "ABC123" từng được lưu thành hai thiết bị khác nhau.
        own_id = None if is_created else getattr(model, "id", None)
        for field in self.unique_text_fields:
            value = data.get(field)
            if not value or not isinstance(value, str):
                continue
            column = getattr(self.model, field)
            stmt = select(self.model.id).where(func.lower(column) == value.lower())
            if hasattr(self.model, "is_deleted"):
                stmt = stmt.where(self.model.is_deleted.is_(False))
            if own_id:
                stmt = stmt.where(self.model.id != own_id)
            with _get_admin_db(request) as db:
                duplicate_id = db.scalar(stmt.limit(1))
            if duplicate_id:
                label = get_property_label(self, field, lang)
                raise ValueError(_msg(
                    lang,
                    f"{label} '{value}' đã tồn tại trong hệ thống (không phân biệt chữ hoa - chữ thường).",
                    f"{label} '{value}' already exists (letter case is ignored).",
                    f"{label}「{value}」はすでに存在します（大文字・小文字は区別されません）。",
                ))

        # BRD: "Hệ thống tự điền" người tạo / người sửa.
        actor_id = request.session.get("user_id")
        if actor_id is not None:
            if "updated_by" in columns:
                data["updated_by"] = int(actor_id)
            if is_created and "created_by" in columns:
                data["created_by"] = int(actor_id)

        # `model` lúc này còn giá trị TRƯỚC khi sửa -> giữ lại để audit có đủ "trước" và "sau".
        if not is_created:
            request.state.itam_audit_before = _column_snapshot(model)

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
            # Khoá cache phải gồm cả tham số lọc (vd. ?action=REVEAL của Audit Log),
            # nếu không tổng số của danh sách đã lọc bị dùng nhầm cho danh sách đầy đủ.
            filters = tuple(sorted(
                (k, str(v)) for k, v in dict(request.query_params).items()
                if k not in _COUNT_CACHE_IGNORED_PARAMS
            ))
            cache_key = (self.model, filters)
            cached = _MODEL_COUNT_CACHE.get(cache_key)
            if cached:
                cached_time, val = cached
                if time.monotonic() - cached_time < _MODEL_COUNT_CACHE_TTL:
                    return val
            val = await super().count(request, stmt)
            _MODEL_COUNT_CACHE[cache_key] = (time.monotonic(), val)
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

            # Chặn xóa danh mục / vai trò còn đang được dùng
            in_use = _in_use_blocker(db, self.model, obj)
            if in_use:
                raise HTTPException(status_code=400, detail=in_use)

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

            # Lý do chỉ gồm khoảng trắng vi phạm CHECK của DB (lỗi 500) -> coi như không nhập.
            # Cột delete_reason là String(300).
            delete_reason = (request.query_params.get("delete_reason") or "").strip()[:300]
            if not delete_reason:
                delete_reason = "Xóa từ giao diện quản trị ITAM"
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

            invalidate_model_count_cache(self.model)
            if self.model in (User, Role):
                invalidate_user_cache()

    async def after_model_change(self, data: dict, model: Any, is_created: bool, request: Request) -> None:
        # Khóa tài khoản / đổi vai trò phải có hiệu lực ngay, không chờ cache 60 giây hết hạn.
        if self.model in (User, Role):
            invalidate_user_cache()

        action = AuditAction.CREATE if is_created else AuditAction.UPDATE
        user_id = request.session.get("user_id")
        record_id = getattr(model, "id", None)
        table_name = getattr(self.model, "__tablename__", "unknown")
        client_ip = request.client.host if request.client else None

        before_snapshot = None if is_created else getattr(request.state, "itam_audit_before", None)
        try:
            after_snapshot: dict[str, Any] = _column_snapshot(model)
        except Exception:
            after_snapshot = data

        try:
            with SessionLocal() as db:
                record_audit(
                    db=db,
                    action=action,
                    table_name=table_name,
                    record_id=record_id,
                    user_id=user_id,
                    before=before_snapshot,
                    after=after_snapshot,
                    ip_address=client_ip,
                )
                db.commit()
        except Exception:
            # Bản ghi chính đã commit xong; không làm hỏng thao tác của người dùng,
            # nhưng mất một dòng audit thì phải để lại dấu vết.
            logger.exception("Không ghi được audit %s cho %s #%s", action.value, table_name, record_id)


# --- Model Views ---

class UserAdmin(BaseAdminView, model=User):
    unique_text_fields = ("username",)
    module = Module.USERS
    name = "Người dùng"
    name_plural = "Tài khoản Đăng nhập"
    icon = "fa-solid fa-users-gear"
    category = "Hệ thống & Phân quyền"
    column_list = [User.username, User.display_name, User.role, User.preferred_lang, User.is_active, User.last_login_at]
    column_details_list = [
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
            "choices": [("vi", "Tiếng Việt (vi)"), ("en", "English (en)"), ("ja", "日本語 (ja)")],
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
            if len(str(raw_password).strip()) < 6:
                raise ValueError("Mật khẩu phải có độ dài tối thiểu 6 ký tự.")
            data["password_hash"] = hash_password(str(raw_password).strip())
        else:
            if raw_password and str(raw_password).strip():
                pwd_clean = str(raw_password).strip()
                if len(pwd_clean) < 6:
                    raise ValueError("Mật khẩu mới phải có độ dài tối thiểu 6 ký tự.")
                data["password_hash"] = hash_password(pwd_clean)

            # Tự khóa hoặc tự hạ vai trò của chính mình có thể làm hệ thống không còn
            # ai quản trị được; việc đó phải do một Admin khác thực hiện.
            current_user_id = request.session.get("user_id")
            if current_user_id is not None and str(getattr(model, "id", "")) == str(current_user_id):
                if "is_active" in data and not data.get("is_active"):
                    raise ValueError("Không thể tự vô hiệu hóa tài khoản của chính bạn đang đăng nhập.")
                new_role_id = _pk_of(data.get("role")) if "role" in data else None
                if new_role_id is not None and new_role_id != getattr(model, "role_id", None):
                    raise ValueError("Không thể tự thay đổi vai trò của chính bạn. Hãy nhờ một Quản trị viên khác thực hiện.")

        await super().on_model_change(data, model, is_created, request)


class RoleAdmin(BaseAdminView, model=Role):
    unique_text_fields = ("code",)
    module = Module.USERS
    name = "Vai trò"
    name_plural = "Vai trò Hệ thống"
    icon = "fa-solid fa-user-shield"
    category = "Hệ thống & Phân quyền"
    column_list = [Role.code, Role.name_en, Role.name_ja]
    column_details_list = [Role.code, Role.name_en, Role.name_ja] + COMMON_EXCLUDED_COLUMNS
    column_labels = {
        "code": "Mã vai trò",
        "name_en": "Tên vai trò (Tiếng Anh/Việt)",
        "name_ja": "Tên vai trò (Tiếng Nhật)",
    }
    form_columns = [Role.code, Role.name_en, Role.name_ja]
    # Đăng nhập chỉ chấp nhận 3 vai trò hệ thống (ADMIN, GA_MANAGER, EXECUTIVE). Vai trò tự
    # tạo gán được cho tài khoản nhưng tài khoản đó không bao giờ đăng nhập được.
    can_create = False

    async def on_model_change(
        self, data: dict, model: Any, is_created: bool, request: Request
    ) -> None:
        # Đăng nhập và phân quyền nhận diện 3 vai trò hệ thống qua `code`.
        # Đổi mã ADMIN là khóa toàn bộ quản trị viên ra khỏi hệ thống.
        old_code = getattr(model, "code", None)
        if not is_created and old_code in SYSTEM_ROLE_CODES:
            new_code = str(data.get("code", old_code) or "").strip()
            if new_code != old_code:
                raise ValueError(f"Không thể đổi mã của vai trò hệ thống '{old_code}'.")
        await super().on_model_change(data, model, is_created, request)






class DepartmentAdmin(BaseAdminView, model=Department):
    unique_text_fields = ("name_en",)
    module = Module.PERSONS
    name = "Phòng ban"
    name_plural = "Danh mục Phòng ban"
    icon = "fa-solid fa-sitemap"
    category = "Danh mục Dùng chung"
    column_list = [Department.name_en, Department.name_ja]
    column_details_list = [Department.name_en, Department.name_ja] + COMMON_EXCLUDED_COLUMNS
    column_labels = {
        "name_en": "Tên phòng ban (Tiếng Anh/Việt)",
        "name_ja": "Tên phòng ban (Tiếng Nhật)",
    }


class AssetCategoryAdmin(BaseAdminView, model=AssetCategory):
    unique_text_fields = ("name_en",)

    async def on_model_change(
        self, data: dict, model: Any, is_created: bool, request: Request
    ) -> None:
        await super().on_model_change(data, model, is_created, request)
        # Loại tài sản là đồ VẬT LÝ. Từng có loại tên "License" khiến 20 license PDF bị nhập
        # thành 20 "thiết bị" và hiện ra trong mọi ô chọn máy.
        lang = _request_lang(request)
        for field in ("name_en", "name_ja"):
            name = str(data.get(field) or "").lower()
            if any(word in name for word in _SOFTWARE_CATEGORY_WORDS):
                raise ValueError(_msg(
                    lang,
                    "Loại tài sản chỉ dành cho thiết bị vật lý. Phần mềm / bản quyền được đánh dấu theo máy ở Sổ tổng.",
                    "Asset categories are for physical devices only. Software is marked per machine in the Ledger.",
                    "資産カテゴリは物理機器専用です。ソフトウェアは台帳で機器ごとに記録してください。",
                ))
    module = Module.ASSETS
    name = "Loại tài sản"
    name_plural = "Danh mục Loại tài sản"
    icon = "fa-solid fa-tags"
    category = "Danh mục Dùng chung"
    column_list = [AssetCategory.name_en, AssetCategory.name_ja]
    column_details_list = [AssetCategory.name_en, AssetCategory.name_ja] + COMMON_EXCLUDED_COLUMNS
    column_labels = {
        "name_en": "Tên loại tài sản (Tiếng Anh/Việt)",
        "name_ja": "Tên loại tài sản (Tiếng Nhật)",
    }


class AssetTagAdmin(BaseAdminView, model=AssetTag):
    # Không hiện trên thanh bên: phần mềm và màu đánh dấu quản lý ngay trên Sổ tổng.
    def is_visible(self, request: Request) -> bool:
        return False

    unique_text_fields = ("code",)
    module = Module.ASSETS
    name = "Nhãn tài sản"
    name_plural = "Danh mục Nhãn (Tags)"
    icon = "fa-solid fa-tag"
    category = "Danh mục Dùng chung"
    column_list = [AssetTag.code, AssetTag.name_en, AssetTag.color]
    column_details_list = [AssetTag.code, AssetTag.name_en, AssetTag.name_ja, AssetTag.color] + COMMON_EXCLUDED_COLUMNS
    column_labels = {
        "code": "Mã nhãn",
        "name_en": "Tên nhãn (Tiếng Anh/Việt)",
        "name_ja": "Tên nhãn (Tiếng Nhật)",
        "color": "Màu nhãn",
    }

    async def on_model_change(
        self, data: dict, model: Any, is_created: bool, request: Request
    ) -> None:
        await super().on_model_change(data, model, is_created, request)
        # Nhãn phần mềm (SW-) và kiểu đánh dấu màu (MARK-) là hai loại khác nhau trên Sổ tổng:
        # đổi mã từ loại này sang loại kia sẽ làm máy âm thầm mất màu hoặc mất phần mềm.
        if is_created or "code" not in data:
            return
        old_code = str(getattr(model, "code", "") or "").upper()
        new_code = str(data.get("code") or "").upper()
        for prefix in ("MARK-", "SW-"):
            if old_code.startswith(prefix) != new_code.startswith(prefix):
                raise ValueError(_msg(
                    _request_lang(request),
                    f"Không được đổi nhãn giữa loại '{prefix}' và loại khác. Hãy tạo nhãn mới.",
                    f"A tag cannot be moved into or out of the '{prefix}' kind. Create a new tag instead.",
                    f"「{prefix}」種別とそれ以外の間でタグを変更できません。新しいタグを作成してください。",
                ))




_PERSON_TYPE_LABEL = {
    PersonType.EMPLOYEE: "Nhân viên chính thức",
    PersonType.VENDOR: "Vendor",
    PersonType.BUSINESS_TRIP: "Công tác Nhật",
}


class PersonAdmin(BaseAdminView, model=Person):
    unique_text_fields = ("staff_code", "email", "user_id")
    module = Module.PERSONS
    name = "Nhân sự"
    name_plural = "Hồ sơ Nhân sự"
    icon = "fa-solid fa-id-card-clip"
    category = "Nhân sự"
    column_list = [Person.staff_code, Person.full_name, Person.person_type, Person.department, Person.status, Person.email, Person.start_working_date]
    column_details_list = [
        Person.staff_code,
        Person.full_name,
        Person.person_type,
        Person.department,
        Person.email,
        Person.user_id,
        Person.status,
        Person.start_working_date,
        Person.note,
    ] + COMMON_EXCLUDED_COLUMNS
    column_searchable_list = [Person.staff_code, Person.full_name, Person.email]
    column_labels = {
        "staff_code": "Mã nhân viên",
        "person_type": "Loại nhân sự",
        "full_name": "Họ và tên nhân viên",
        "department": "Phòng ban",
        "status": "Tình trạng",
        "email": "Email",
        "start_working_date": "Ngày vào làm việc",
        "user_id": "UserID",
        "note": "Ghi chú",
    }
    column_formatters = {
        "person_type": lambda m, a: translate(_PERSON_TYPE_LABEL.get(m.person_type, ""), get_admin_lang()),
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
        "person_type": lambda m, a: translate(_PERSON_TYPE_LABEL.get(m.person_type, ""), get_admin_lang()),
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

    async def on_model_change(
        self, data: dict, model: Any, is_created: bool, request: Request
    ) -> None:
        await super().on_model_change(data, model, is_created, request)
        if is_created or "staff_code" in data or "person_type" in data:
            # Mã phải khớp loại nhân sự; vendor / công tác Nhật để trống mã thì app tự cấp.
            person_type = (
                _enum_of(PersonType, data.get("person_type")) if "person_type" in data else None
            ) or getattr(model, "person_type", None) or PersonType.EMPLOYEE
            code = data["staff_code"] if "staff_code" in data else getattr(model, "staff_code", None)
            with _get_admin_db(request) as db:
                data["staff_code"] = person_code_service.resolve_code(db, person_type, code)
        new_status = _enum_of(PersonStatus, data.get("status")) if "status" in data else None
        person_id = None if is_created else getattr(model, "id", None)
        # Chỉ chặn lúc CHUYỂN sang "đã nghỉ"; người đã nghỉ từ trước (dữ liệu cũ) vẫn sửa hồ sơ được.
        if new_status != PersonStatus.RESIGNED or not person_id or getattr(model, "status", None) == PersonStatus.RESIGNED:
            return
        lang = _request_lang(request)
        with _get_admin_db(request) as db:
            assets = db.scalar(select(func.count()).select_from(Assignment).where(
                Assignment.person_id == person_id, Assignment.returned_at.is_(None), Assignment.is_deleted.is_(False),
            )) or 0
        if assets:
            raise ValueError(_msg(
                lang,
                f"Nhân sự này còn đang giữ {assets} thiết bị. Hãy thu hồi hết trước khi chuyển sang 'Đã nghỉ việc'.",
                f"This person still holds {assets} asset(s). Return them all before marking the person as resigned.",
                f"この社員は機器 {assets} 台を保持しています。退職に変更する前にすべて回収してください。",
            ))

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
        return await self._get_object_by_pk(stmt)


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
    unique_text_fields = ("device_code", "serial")
    module = Module.ASSETS
    name = "Tài sản IT"
    name_plural = "Danh sách Thiết bị"
    icon = "fa-solid fa-laptop"
    category = "Tài sản"
    column_list = [
        Asset.device_code,
        Asset.serial,
        Asset.category,
        "status_badge",
        "current_holder",
        Asset.model,
        "actions_quick",
    ]
    column_details_list = [
        Asset.device_code,
        Asset.serial,
        Asset.category,
        Asset.status,
        "current_holder",
        Asset.model,
        Asset.form_factor,
        Asset.hwid,
        Asset.mac_ethernet,
        Asset.mac_wifi,
        Asset.note,
    ] + COMMON_EXCLUDED_COLUMNS
    column_labels = {
        "status_badge": "Trạng thái",
        "current_holder": "Người đang sử dụng",
        "actions_quick": "Thao tác nhanh",
        "device_code": "Mã thiết bị",
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
                f'data-id="{m.id}" data-code="{escape(m.device_code)}" data-model="{escape(m.model or "")}" '
                f'onclick="openAssignModal(this.dataset.id, this.dataset.code, this.dataset.model)" style="font-size: 11.5px;">'
                f'<i class="fa-solid fa-handshake me-1"></i>{translate("Bàn giao", get_admin_lang())}</button>'
            )
            if m.status == AssetStatus.IN_STOCK and user_can_loan(current_request_ctx.get())
            else (
                Markup(
                    f'<button type="button" class="btn btn-sm btn-outline-warning text-dark py-0 px-2 fw-bold" '
                    f'data-id="{m.id}" data-code="{escape(m.device_code)}" data-holder="{escape(m.current_holder or "")}" '
                    f'onclick="openReturnModal(this.dataset.id, this.dataset.code, this.dataset.holder)" style="font-size: 11.5px;">'
                    f'<i class="fa-solid fa-arrow-rotate-left me-1"></i>{translate("Thu hồi", get_admin_lang())}</button>'
                )
                if m.status == AssetStatus.IN_USE and user_can_loan(current_request_ctx.get())
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
    column_searchable_list = [Asset.device_code, Asset.serial, Asset.model]
    form_excluded_columns = COMMON_EXCLUDED_COLUMNS + ["assignments"]

    def list_query(self, request: Request) -> Select:
        stmt = super().list_query(request)
        return stmt.options(
            selectinload(Asset.assignments).selectinload(Assignment.person)
        )

    async def on_model_change(
        self, data: dict, model: Any, is_created: bool, request: Request
    ) -> None:
        await super().on_model_change(data, model, is_created, request)
        lang = _request_lang(request)
        asset_id = None if is_created else getattr(model, "id", None)

        with _get_admin_db(request) as db:
            # 1. Trạng thái IN_USE chỉ được sinh ra/mất đi qua nghiệp vụ Bàn giao - Thu hồi.
            #    Gõ tay làm lệch trạng thái với lịch sử mượn: máy "trong kho" nhưng vẫn có
            #    người giữ, hoặc máy IN_USE không ai giữ và không thu hồi/xóa được.
            desired = _enum_of(AssetStatus, data.get("status")) if "status" in data else None
            # Chỉ kiểm khi trạng thái thật sự thay đổi: dữ liệu cũ có thể đã lệch sẵn, và
            # người dùng chỉ sửa ghi chú không nên bị chặn vì một trạng thái họ không đụng tới.
            if desired is not None and not is_created and desired == getattr(model, "status", None):
                desired = None
            if desired is not None:
                has_open = False
                if asset_id:
                    has_open = bool(db.scalar(
                        select(Assignment.id).where(
                            Assignment.asset_id == asset_id,
                            Assignment.returned_at.is_(None),
                            Assignment.is_deleted.is_(False),
                        ).limit(1)
                    ))
                if desired == AssetStatus.IN_USE and not has_open:
                    raise ValueError(_msg(
                        lang,
                        "Không thể tự đặt trạng thái 'Đang sử dụng' khi thiết bị chưa được bàn giao cho ai. "
                        "Hãy dùng nút 'Bàn giao' để cấp phát thiết bị.",
                        "Status 'IN_USE' cannot be set by hand. Use the 'Assign' action to hand the asset over.",
                        "貸出記録がないため、ステータスを「使用中」に手動で設定することはできません。「貸出」操作を使用してください。",
                    ))
                if desired != AssetStatus.IN_USE and has_open:
                    raise ValueError(_msg(
                        lang,
                        "Thiết bị đang được bàn giao cho nhân viên. Hãy 'Thu hồi' thiết bị trước khi đổi trạng thái.",
                        "This asset is currently on loan. Return it before changing its status.",
                        "この機器は現在貸出中です。ステータスを変更する前に返却処理を行ってください。",
                    ))

    async def get_object_for_details(self, value: Any) -> Any:
        stmt = self._stmt_by_identifier(value)
        stmt = stmt.options(
            selectinload(Asset.category),
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
        Assignment.asset,
        Assignment.person,
        "status_badge",
        Assignment.borrowed_at,
        Assignment.returned_at,
        "actions_quick",
    ]
    column_details_list = [
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
                f'data-id="{m.asset_id}" data-code="{escape(m.asset.device_code if m.asset else "")}" data-holder="{escape(m.person.full_name if m.person else "")}" '
                f'onclick="openReturnModal(this.dataset.id, this.dataset.code, this.dataset.holder)" style="font-size: 11.5px;">'
                f'<i class="fa-solid fa-arrow-rotate-left me-1"></i>{translate("Thu hồi", get_admin_lang())}</button>'
            )
            if not m.returned_at and user_can_loan(current_request_ctx.get())
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
        lang = _request_lang(request)
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

        # `model` ở đây còn mang giá trị TRƯỚC khi sửa.
        old_aid = None if is_created else getattr(model, "asset_id", None)
        old_pid = None if is_created else getattr(model, "person_id", None)
        was_open = (not is_created) and getattr(model, "returned_at", None) is None
        request.state.itam_prev_asset_id = old_aid
        pid = _form_fk(data, "person", model, "person_id")

        # Bất biến số 7: lịch sử không được ghi đè. Dòng đã đóng chỉ được đính chính
        # ngày và ghi chú, không được đổi thành "máy khác" hay "người khác".
        if not is_created and not was_open and (aid != old_aid or pid != old_pid):
            raise ValueError(_msg(
                lang,
                "Lượt bàn giao này đã đóng. Không thể đổi thiết bị hoặc nhân viên của một dòng lịch sử.",
                "This assignment is closed. The asset or person of a history row cannot be changed.",
                "この割当は終了済みです。履歴の機器・担当者は変更できません。",
            ))

        # Lượt bàn giao sẽ ở trạng thái MỞ sau khi lưu -> áp cùng luật với assign_asset().
        # Không áp khi chỉ đóng lượt mượn: người đã nghỉ việc vẫn phải trả được máy.
        if aid and r_at is None:
            asset_is_new_target = is_created or not was_open or aid != old_aid
            person_is_new_target = is_created or not was_open or pid != old_pid
            with _get_admin_db(request) as db:
                asset = db.get(Asset, aid)
                if not asset or asset.is_deleted:
                    raise ValueError(_msg(
                        lang,
                        "Thiết bị được chọn không tồn tại hoặc đã bị xóa.",
                        "The selected asset does not exist or has been deleted.",
                        "選択された機器は存在しないか、削除されています。",
                    ))
                if asset_is_new_target and asset.status in (AssetStatus.DISPOSED, AssetStatus.LOST, AssetStatus.REPAIR):
                    raise ValueError(_msg(
                        lang,
                        f"Không thể bàn giao thiết bị ở trạng thái '{asset.status.value}'.",
                        f"An asset in status '{asset.status.value}' cannot be assigned.",
                        f"ステータスが「{asset.status.value}」の機器は貸出できません。",
                    ))
                if pid and person_is_new_target:
                    _require_active_person(db, pid, lang)

        today = today_local()
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

        # Chạy cả khi ngày giao để trống (không rõ ngày): vẫn phải chặn hai lượt cùng mở trên một máy.
        if aid:
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
                        if o_start and ((b_at and b_at >= o_start) or (r_at and r_at > o_start)):
                            if is_ja:
                                raise ValueError(f"割当期間の重複: この機器は {o_start} から '{holder}' が使用中です。")
                            elif is_en:
                                raise ValueError(f"Overlapping asset assignment period: This asset is in use by '{holder}' since {o_start}.")
                            else:
                                raise ValueError(f"Trùng lặp thời gian cấp phát: Thiết bị này đang được bàn giao cho '{holder}' từ ngày {o_start.strftime('%d/%m/%Y')} (chưa thu hồi). Thời gian cấp phát mới không thể trùng lấn với người đang sử dụng.")
                    else:
                        # Ngày giao không rõ thì không đối chiếu được với lượt đã đóng.
                        if b_at and b_at < o_end and (r_at is None or o_start is None or r_at > o_start):
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
                                    f"từ ngày {o_start.strftime('%d/%m/%Y') if o_start else 'không rõ'} đến ngày {o_end.strftime('%d/%m/%Y')}. "
                                    f"Thời gian cấp phát ({b_at.strftime('%d/%m/%Y')} - {r_at.strftime('%d/%m/%Y') if r_at else 'chưa thu hồi'}) "
                                    f"bị trùng lấn với lượt bàn giao trước."
                                )


    async def after_model_change(
        self, data: dict, model: Any, is_created: bool, request: Request
    ) -> None:
        await super().after_model_change(data, model, is_created, request)
        # Đồng bộ cả thiết bị CŨ nếu form đổi sang thiết bị khác, nếu không máy cũ
        # kẹt ở IN_USE mà không có lượt bàn giao nào để thu hồi.
        asset_ids = {getattr(request.state, "itam_prev_asset_id", None), getattr(model, "asset_id", None)}
        asset_ids.discard(None)
        if not asset_ids:
            return
        user_id = request.session.get("user_id")
        client_ip = request.client.host if request.client else None
        try:
            with SessionLocal() as db:
                for asset_id in sorted(asset_ids):
                    _sync_asset_status(db, asset_id, user_id, client_ip)
                db.commit()
        except Exception:
            logger.exception("Không đồng bộ được trạng thái thiết bị sau khi lưu lượt bàn giao #%s", getattr(model, "id", None))


























def _valid_audit_action(raw: str | None) -> str | None:
    """Giá trị ?action= hợp lệ, hoặc None. Chuỗi lạ đưa thẳng xuống ENUM của PostgreSQL sẽ thành lỗi 500."""
    return raw if raw in {a.value for a in AuditAction} else None


def _audit_record_label(table: str | None, record_id: int | None) -> str:
    """Tên dễ đọc của bản ghi trong nhật ký (mã thiết bị, mã nhân viên, tên danh mục) thay cho số ID."""
    if record_id is None:
        return "-"
    try:
        with SessionLocal() as db:
            if table == "assets":
                label = db.scalar(select(Asset.device_code).where(Asset.id == record_id))
            elif table in ("persons", "person_secrets"):
                row = db.execute(select(Person.staff_code, Person.full_name).where(Person.id == record_id)).first()
                label = f"{row[0]} · {row[1]}" if row else None
            elif table == "assignments":
                row = db.execute(
                    select(Asset.device_code, Person.staff_code)
                    .join(Assignment, Assignment.asset_id == Asset.id)
                    .join(Person, Person.id == Assignment.person_id)
                    .where(Assignment.id == record_id)
                ).first()
                label = f"{row[0]} → {row[1]}" if row else None
            elif table == "departments":
                label = db.scalar(select(Department.name_en).where(Department.id == record_id))
            elif table == "asset_categories":
                label = db.scalar(select(AssetCategory.name_en).where(AssetCategory.id == record_id))
            elif table == "asset_tags":
                label = db.scalar(select(AssetTag.name_en).where(AssetTag.id == record_id))
            elif table == "users":
                label = db.scalar(select(User.username).where(User.id == record_id))
            elif table == "roles":
                label = db.scalar(select(Role.code).where(Role.id == record_id))
            else:
                label = None
    except Exception:  # nhật ký vẫn phải mở được dù tra tên lỗi
        logger.exception("Không tra được tên bản ghi %s #%s", table, record_id)
        label = None
    return label or f"#{record_id}"


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
        AuditLog.created_at,
        AuditLog.user,
        AuditLog.action,
        AuditLog.table_name,
        AuditLog.record_id,
        "summary",
        AuditLog.ip_address,
    ]
    column_details_list = [
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
        "record_id": "Bản ghi",
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
    # Các dòng ghi trong cùng một giao dịch có created_at trùng nhau -> thêm id để phân trang ổn định.
    column_default_sort = [(AuditLog.created_at, True), (AuditLog.id, True)]
    column_searchable_list = [
        AuditLog.table_name,
        AuditLog.action,
        AuditLog.ip_address,
    ]
    column_formatters = {
        "record_id": lambda m, a: _audit_record_label(m.table_name, m.record_id),
        "summary": lambda m, a: m.summary or "-",
    }
    column_formatters_detail = {
        "record_id": lambda m, a: _audit_record_label(m.table_name, m.record_id),
        "summary": lambda m, a: m.summary or "-",
    }

    def list_query(self, request: Request) -> Select:
        stmt = super().list_query(request)
        stmt = stmt.options(selectinload(AuditLog.user))
        act = _valid_audit_action(request.query_params.get("action"))
        if act:
            stmt = stmt.where(AuditLog.action == act)
        tbl = request.query_params.get("table")
        if tbl:
            stmt = stmt.where(AuditLog.table_name == tbl)
        return stmt

    def count_query(self, request: Request) -> Select:
        stmt = super().count_query(request)
        act = _valid_audit_action(request.query_params.get("action"))
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
            # Phải dùng đúng phép kiểm tra của trang trong (tài khoản còn hoạt động, vai trò
            # hợp lệ). Chỉ kiểm chữ ký token thì tài khoản vừa bị khóa sẽ bị đẩy qua lại
            # giữa /admin và /admin/login đến khi trình duyệt báo lỗi.
            had_token = bool(request.session.get("token") or request.cookies.get("itam_session"))
            if had_token and await self.authentication_backend.authenticate(request):
                return RedirectResponse(request.url_for("admin:index"), status_code=302)
            response = await self.templates.TemplateResponse(request, "sqladmin/login.html")
            if had_token:
                request.session.clear()
                response.delete_cookie("itam_session", path="/")
            return response

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
        # Cookie được gia hạn theo thao tác còn token trong admin_session thì không, nên
        # phải thử cả hai (cùng thứ tự với authenticate) rồi mới đến user_id của session.
        revoke_user_id = None
        for token in (request.cookies.get("itam_session"), request.session.get("token")):
            payload = verify_session_token(token) if token else None
            if payload and "user_id" in payload:
                revoke_user_id = payload["user_id"]
                break
        if revoke_user_id is None:
            revoke_user_id = request.session.get("user_id")
        if revoke_user_id is not None:
            try:
                from app.routers.auth import reveal_gate
                reveal_gate.revoke(int(revoke_user_id))
            except Exception:
                logger.exception("Không thu hồi được token xem mật khẩu khi đăng xuất")

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
        """Sổ tổng là trang làm việc chính; trang tổng quan cũ đã được gỡ."""
        return RedirectResponse("/admin/so-tong", status_code=302)


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
    admin.templates.env.globals["can"] = user_can
    admin.templates.env.globals["can_loan"] = user_can_loan
    admin.templates.env.globals["humanize_error"] = humanize_error_str
    admin.templates.env.filters["humanize_error"] = humanize_error_str
    admin.templates.env.globals["get_property_label"] = get_property_label
    admin.templates.env.filters["get_property_label"] = get_property_label
    admin.templates.env.globals["format_datetime_clean"] = format_datetime_clean
    admin.templates.env.filters["format_datetime_clean"] = format_datetime_clean

    # 1. Hệ thống & phân quyền
    admin.add_view(UserAdmin)
    admin.add_view(RoleAdmin)

    # 2. Danh mục dùng chung
    admin.add_view(DepartmentAdmin)
    admin.add_view(AssetCategoryAdmin)
    admin.add_view(AssetTagAdmin)

    # 3. Nhân sự
    admin.add_view(PersonAdmin)
    admin.add_view(PersonSecretAdmin)

    # 4. Tài sản
    admin.add_view(AssetAdmin)
    admin.add_view(AssignmentAdmin)

    # 9. Truy vết
    admin.add_view(AuditLogAdmin)

    global _admin_instance
    _admin_instance = admin

    return admin
