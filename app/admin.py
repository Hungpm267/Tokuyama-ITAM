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
from wtforms.validators import InputRequired
from wtforms.widgets import PasswordInput
from app.db import SessionLocal
from app.enums import (
    AssetStatus,
    AuditAction,
    CardStatus,
    ContractItemKind,
    Module,
    PermissionAction,
    PersonStatus,
    RoleCode,
)
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
from app.services.contract_service import line_received_qty, sync_contract_delivery_status

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
            LicenseProduct: [(License, "product_id", "gói bản quyền")],
            Location: [(Phone, "location_id", "thiết bị thoại")],
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


def _can_receive_line(line: Any) -> bool:
    """Nhận phần cứng cần (assets, add); nhận phần mềm cần (licenses, add)."""
    module = "licenses" if line.item_kind == ContractItemKind.SOFTWARE else "assets"
    return user_can(current_request_ctx.get(), module, "add")


def _csv_safe(value: Any) -> str:
    """Giá trị văn bản an toàn cho Excel: ô bắt đầu bằng = + - @ sẽ bị chạy như công thức."""
    text_val = "" if value is None else str(value)
    if text_val and text_val[0] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + text_val
    return text_val


#: Từ khóa cho thấy một "loại tài sản" thực ra là phần mềm - phải quản lý ở Kho License.
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


def _sync_card_status(db: Session, card_id: int, user_id: Any, ip_address: str | None) -> None:
    """Chỉ chuyển qua lại IN_STOCK <-> BORROWED. LOST/DAMAGED do người dùng đặt và phải được giữ nguyên."""
    card = db.get(AccessCard, card_id)
    if not card:
        return
    has_open = db.scalar(
        select(CardLoan.id).where(
            CardLoan.card_id == card.id,
            CardLoan.returned_at.is_(None),
            CardLoan.is_deleted.is_(False),
        ).limit(1)
    )
    old_status = card.status
    if has_open and old_status == CardStatus.IN_STOCK:
        new_status = CardStatus.BORROWED
    elif not has_open and old_status == CardStatus.BORROWED:
        new_status = CardStatus.IN_STOCK
    else:
        return
    card.status = new_status
    record_audit(
        db=db,
        action=AuditAction.UPDATE,
        table_name="access_cards",
        record_id=card.id,
        user_id=user_id,
        before={"status": old_status.value},
        after={"status": new_status.value},
        ip_address=ip_address,
    )


def _receive_url(line: Any) -> str:
    """Màn hình nhận hàng đúng với loại hạng mục: nhập serial (phần cứng) hay ghi nhận gói phần mềm."""
    if line.item_kind == ContractItemKind.SOFTWARE:
        return f"/admin/contract-line/{line.id}/receive-software"
    return f"/admin/contract-line/{line.id}/receive"


def _receive_label(line: Any, hardware_label: str) -> str:
    key = "Nhận phần mềm" if line.item_kind == ContractItemKind.SOFTWARE else hardware_label
    return translate(key, get_admin_lang())


def _sync_contracts_of_lines(db: Session, line_ids: set) -> None:
    contract_ids = {
        line.contract_id
        for line in (db.get(ContractLine, lid) for lid in line_ids if lid)
        if line
    }
    for contract_id in sorted(contract_ids):
        sync_contract_delivery_status(db, contract_id)


def _open_license_assignments(db: Session, license_id: int, exclude_id: int | None = None) -> int:
    stmt = select(func.count(LicenseAssignment.id)).where(
        LicenseAssignment.license_id == license_id,
        LicenseAssignment.removed_at.is_(None),
        LicenseAssignment.is_deleted.is_(False),
    )
    if exclude_id:
        stmt = stmt.where(LicenseAssignment.id != exclude_id)
    return db.scalar(stmt) or 0


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
    # Cắt phần "[SQL: INSERT INTO assets (asset_code, vendor_code, serial...)]" trước khi
    # so khớp: câu SQL liệt kê mọi cột nên trùng asset_code từng bị báo thành trùng serial.
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
    if "no_na_literal" in m:
        return _tr("Không nhập 'N/A' vào ô này. Nếu không có giá trị, hãy để trống.", "Do not type 'N/A'. Leave the field empty if there is no value.", "「N/A」は入力できません。値がない場合は空欄にしてください。")
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
        if "uq_open_license_assignments_license_id_asset_id" in m:
            return _tr(
                "Thiết bị này đã được gán gói bản quyền này từ trước (chưa thu hồi). Một thiết bị không thể nhận 2 bản quyền cùng loại cùng lúc. Vui lòng cập nhật Ngày thu hồi (removed_at) ở lượt gán trước trước khi gán lại.",
                "This device already has an active assignment for this license. Please record the removal date on the existing assignment before reassigning.",
                "この機器にはすでにこのライセンスが割り当てられています（未返却）。再割り当てする前に回収日を入力してください。",
            )
        if "uq_open_license_assignments_license_id_person_id" in m:
            return _tr(
                "Nhân sự này đã được gán gói bản quyền này từ trước (chưa thu hồi). Một nhân sự không thể nhận 2 bản quyền cùng loại cùng lúc. Vui lòng cập nhật Ngày thu hồi (removed_at) ở lượt gán trước trước khi gán lại.",
                "This person already has an active assignment for this license. Please record the removal date on the existing assignment before reassigning.",
                "この担当者にはすでにこのライセンスが割り当てられています（未返却）。再割り当てする前に回収日を入力してください。",
            )
        if "uq_open_assignments_asset_id" in m:
            return _tr(
                "Thiết bị này hiện đang được bàn giao cho nhân viên khác sử dụng (chưa thu hồi). Vui lòng cập nhật Ngày thu hồi ở lượt bàn giao trước đó trước khi bàn giao lại.",
                "This asset is currently in use and has not been returned yet. Please record the return date before reassigning.",
                "この機器は現在他の担当者に貸出中です（未返却）。再貸出する前に前回の返却日を入力してください。",
            )
        if "uq_open_card_loans_card_id" in m:
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
        if "email" in m:
            return _tr("Email này đã được dùng cho một nhân sự khác (bị trùng lặp).", "Email already belongs to another employee.", "このEmailはすでに別の社員に使用されています。")
        if "extension_number" in m:
            return _tr("Số máy nhánh này đã tồn tại trong hệ thống (bị trùng lặp).", "Extension number already exists in system.", "この内線番号はすでにシステムに存在します。")
        if "device_name" in m:
            return _tr("Tên thiết bị thoại này đã tồn tại trong hệ thống (bị trùng lặp).", "Phone device name already exists in system.", "この電話機器名はすでにシステムに存在します。")
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
        # License hết hạn vẫn chọn được (chủ hệ thống quyết định chỉ cảnh báo), nhưng
        # người chọn phải thấy ngay là gói đã hết hạn.
        expiry = getattr(obj, "expiry_date", None) if isinstance(obj, License) else None
        if expiry and expiry < today_local():
            label = f"{label} ⚠ {translate('đã hết hạn', get_admin_lang())} {expiry.strftime('%d/%m/%Y')}"
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

                # Bản quyền gán theo máy vẫn chiếm seat sau khi máy bị xóa -> phải thu hồi trước
                active_lic = db.scalar(
                    select(LicenseAssignment).where(
                        LicenseAssignment.asset_id == obj.id,
                        LicenseAssignment.removed_at.is_(None),
                        LicenseAssignment.is_deleted.is_(False),
                    )
                )
                if active_lic:
                    raise HTTPException(
                        status_code=400,
                        detail="Không thể xóa thiết bị đang được gán bản quyền phần mềm. Hãy thu hồi license trước khi xóa.",
                    )

            # Chặn xóa License khi còn lượt gán đang mở (BRD: phải thu hồi trước)
            if self.model is License:
                open_count = _open_license_assignments(db, obj.id)
                if open_count > 0:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Không thể xóa bản quyền đang được gán cho {open_count} máy/nhân viên. Hãy thu hồi license trước khi xóa.",
                    )

            # Chặn xóa Hợp đồng khi còn hạng mục: hạng mục mồ côi vẫn nhận hàng được
            if self.model is Contract:
                live_lines = db.scalar(
                    select(func.count(ContractLine.id)).where(
                        ContractLine.contract_id == obj.id,
                        ContractLine.is_deleted.is_(False),
                    )
                ) or 0
                if live_lines > 0:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Không thể xóa hợp đồng còn {live_lines} hạng mục. Hãy xóa các hạng mục trước.",
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
                linked_licenses = db.scalar(
                    select(func.count(License.id)).where(
                        License.contract_line_id == obj.id,
                        License.is_deleted.is_(False),
                    )
                ) or 0
                if linked_licenses > 0:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Không thể xóa dòng hợp đồng đã nhận {linked_licenses} gói phần mềm.",
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

                # Xóa mềm thiết bị / gói license / hạng mục làm thay đổi "đã nhận đủ hay chưa"
                # của hợp đồng liên quan -> tính lại.
                if self.model in (Asset, License) and getattr(obj, "contract_line_id", None):
                    line = db.get(ContractLine, obj.contract_line_id)
                    if line:
                        db.flush()
                        sync_contract_delivery_status(db, line.contract_id)
                elif self.model is ContractLine:
                    db.flush()
                    sync_contract_delivery_status(db, obj.contract_id)

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
    column_list = [Role.id, Role.code, Role.name_en, Role.name_ja]
    column_details_list = [Role.id, Role.code, Role.name_en, Role.name_ja] + COMMON_EXCLUDED_COLUMNS
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


class RolePermissionAdmin(BaseAdminView, model=RolePermission):
    module = Module.USERS
    name = "Quyền vai trò"
    name_plural = "Ma trận Quyền Vai trò"
    icon = "fa-solid fa-key"
    category = "Hệ thống & Phân quyền"
    list_template = "sqladmin/role_permission_matrix.html"
    # Quyền vai trò chỉ sửa qua Ma trận: form từng dòng cho gõ tự do tên phân hệ (gõ sai là
    # thành quyền vô nghĩa) và đi vòng qua kiểm tra chống tự khóa quyền ADMIN.
    can_create = False
    can_edit = False
    can_delete = False
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

    async def scaffold_form(self, rules: list[str] | None = None) -> type[Form]:
        """SQLAdmin bỏ cột khóa ngoại `user_id` khỏi form (model không có quan hệ `user`),
        nên trước đây mọi lần lưu đều lỗi NOT NULL. Phân hệ và thao tác là danh sách chọn
        để không gõ sai thành quyền vô nghĩa."""
        base_form = await super().scaffold_form(rules)

        with SessionLocal() as db:
            users = db.scalars(
                select(User).where(User.is_deleted.is_(False)).order_by(User.username)
            ).all()
            user_choices = [(u.id, f"{u.username} ({u.display_name or u.username})") for u in users]

        class OverrideForm(base_form):
            user_id = SelectField(
                "Người dùng", choices=user_choices, coerce=int,
                validators=[InputRequired()], render_kw={"class": "form-control"},
            )
            module = SelectField(
                "Phân hệ nghiệp vụ", choices=[(m.value, m.value) for m in Module],
                render_kw={"class": "form-control"},
            )
            action = SelectField(
                "Thao tác", choices=[(a.value, a.value) for a in PermissionAction],
                render_kw={"class": "form-control"},
            )

        return OverrideForm

    async def after_model_change(
        self, data: dict, model: Any, is_created: bool, request: Request
    ) -> None:
        await super().after_model_change(data, model, is_created, request)
        invalidate_user_cache()


class DepartmentAdmin(BaseAdminView, model=Department):
    unique_text_fields = ("code", "name_en")
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
                    "Loại tài sản chỉ dành cho thiết bị vật lý. Phần mềm / bản quyền được quản lý ở mục "
                    "License (Danh mục Phần mềm, Kho License Phần mềm) và nhận hàng qua hạng mục hợp đồng loại 'Phần mềm'.",
                    "Asset categories are for physical devices only. Software is managed under License "
                    "(software catalogue and license packages) and received through 'Software' contract lines.",
                    "資産カテゴリは物理機器専用です。ソフトウェアは License メニューで管理し、区分「ソフトウェア」の契約明細で受入してください。",
                ))
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
    unique_text_fields = ("code",)
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
    unique_text_fields = ("staff_code", "email", "user_login_id")
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

    async def on_model_change(
        self, data: dict, model: Any, is_created: bool, request: Request
    ) -> None:
        await super().on_model_change(data, model, is_created, request)
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
            cards = db.scalar(select(func.count()).select_from(CardLoan).where(
                CardLoan.person_id == person_id, CardLoan.returned_at.is_(None), CardLoan.is_deleted.is_(False),
            )) or 0
            licenses = db.scalar(select(func.count()).select_from(LicenseAssignment).where(
                LicenseAssignment.person_id == person_id, LicenseAssignment.removed_at.is_(None),
                LicenseAssignment.is_deleted.is_(False),
            )) or 0
        if assets or cards or licenses:
            raise ValueError(_msg(
                lang,
                f"Nhân sự này còn đang giữ {assets} thiết bị, {cards} thẻ ra vào, {licenses} bản quyền phần mềm. "
                "Hãy thu hồi hết trước khi chuyển sang 'Đã nghỉ việc'.",
                f"This person still holds {assets} asset(s), {cards} access card(s) and {licenses} license seat(s). "
                "Return / revoke them all before marking the person as resigned.",
                f"この社員は機器 {assets} 台、入館カード {cards} 枚、ライセンス {licenses} 件を保持しています。"
                "退職に変更する前にすべて回収してください。",
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
    unique_text_fields = ("asset_code", "vendor_code", "serial")
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
            if m.status == AssetStatus.IN_STOCK and user_can_loan(current_request_ctx.get())
            else (
                Markup(
                    f'<button type="button" class="btn btn-sm btn-outline-warning text-dark py-0 px-2 fw-bold" '
                    f'data-id="{m.id}" data-code="{escape(m.asset_code or m.serial or "")}" data-holder="{escape(m.current_holder or "")}" '
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
    column_searchable_list = [Asset.asset_code, Asset.serial, Asset.vendor_code, Asset.model]
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
            if desired in (AssetStatus.DISPOSED, AssetStatus.LOST) and asset_id:
                seat = db.scalar(
                    select(LicenseAssignment.id).where(
                        LicenseAssignment.asset_id == asset_id,
                        LicenseAssignment.removed_at.is_(None),
                        LicenseAssignment.is_deleted.is_(False),
                    ).limit(1)
                )
                if seat:
                    raise ValueError(_msg(
                        lang,
                        "Thiết bị đang được gán bản quyền phần mềm. Hãy thu hồi license trước khi thanh lý / báo mất, "
                        "nếu không seat sẽ bị một máy không còn dùng chiếm giữ.",
                        "This asset still holds software license seats. Revoke them before disposing of it or marking it lost.",
                        "この機器にはライセンスが割り当てられています。廃棄・紛失にする前にライセンスを回収してください。",
                    ))
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

            # 2. Số đã nhận của hạng mục hợp đồng được ĐẾM từ assets.contract_line_id (Rule 8),
            #    nên gắn máy vào hạng mục qua form cũng phải tôn trọng số lượng đặt mua.
            if "contract_line" in data:
                old_line_id = None if is_created else getattr(model, "contract_line_id", None)
                new_line_id = _pk_of(data.get("contract_line"))
                request.state.itam_prev_contract_line_id = old_line_id
                if new_line_id and new_line_id != old_line_id:
                    line = db.get(ContractLine, new_line_id)
                    if not line or line.is_deleted:
                        raise ValueError(_msg(
                            lang,
                            "Hạng mục hợp đồng được chọn không tồn tại hoặc đã bị xóa.",
                            "The selected contract line does not exist or has been deleted.",
                            "選択された契約明細は存在しないか、削除されています。",
                        ))
                    if line.item_kind == ContractItemKind.SOFTWARE:
                        raise ValueError(_msg(
                            lang,
                            "Hạng mục hợp đồng này là phần mềm, không thể gắn thiết bị vào. "
                            "Hãy dùng nút 'Nhận phần mềm' ở hạng mục đó.",
                            "This contract line is for software; a hardware asset cannot be attached to it.",
                            "この契約明細はソフトウェア用のため、機器を紐付けることはできません。",
                        ))
                    received = line_received_qty(db, line, exclude_asset_id=asset_id)
                    if received >= line.qty_ordered:
                        raise ValueError(_msg(
                            lang,
                            f"Hạng mục hợp đồng này đã nhận đủ {line.qty_ordered}/{line.qty_ordered} thiết bị, không thể gắn thêm.",
                            f"This contract line is already fully received ({line.qty_ordered}/{line.qty_ordered}).",
                            f"この契約明細はすでに全数（{line.qty_ordered}/{line.qty_ordered}）受領済みです。",
                        ))

    async def after_model_change(
        self, data: dict, model: Any, is_created: bool, request: Request
    ) -> None:
        await super().after_model_change(data, model, is_created, request)
        if "contract_line" not in data:
            return
        line_ids = {
            getattr(request.state, "itam_prev_contract_line_id", None),
            getattr(model, "contract_line_id", None),
        }
        line_ids.discard(None)
        if not line_ids:
            return
        try:
            with SessionLocal() as db:
                _sync_contracts_of_lines(db, line_ids)
                db.commit()
        except Exception:
            logger.exception("Không đồng bộ được tiến độ hợp đồng sau khi lưu thiết bị #%s", getattr(model, "id", None))

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


class LicenseProductAdmin(BaseAdminView, model=LicenseProduct):
    unique_text_fields = ("name",)
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
        License.contract_line,
        License.note,
    ] + COMMON_EXCLUDED_COLUMNS
    column_labels = {
        "contract_line": "Hạng mục hợp đồng",
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

    async def on_model_change(
        self, data: dict, model: Any, is_created: bool, request: Request
    ) -> None:
        await super().on_model_change(data, model, is_created, request)
        lang = _request_lang(request)
        new_seats = data.get("seats")
        license_id = None if is_created else getattr(model, "id", None)
        seats_after = int(new_seats) if new_seats is not None else (getattr(model, "seats", None) or 0)

        # `model` còn mang giá trị TRƯỚC khi sửa.
        old_line_id = None if is_created else getattr(model, "contract_line_id", None)
        new_line_id = _pk_of(data.get("contract_line")) if "contract_line" in data else old_line_id
        request.state.itam_prev_license_line_id = old_line_id

        with _get_admin_db(request) as db:
            if license_id and "product" in data:
                new_product_id = _pk_of(data.get("product"))
                if new_product_id is not None and new_product_id != getattr(model, "product_id", None):
                    ever_assigned = db.scalar(
                        select(LicenseAssignment.id).where(
                            LicenseAssignment.license_id == license_id,
                            LicenseAssignment.is_deleted.is_(False),
                        ).limit(1)
                    )
                    if ever_assigned:
                        raise ValueError(_msg(
                            lang,
                            "Gói bản quyền này đã có lịch sử cấp phát. Đổi sản phẩm sẽ làm mọi dòng lịch sử "
                            "hiện sai tên phần mềm - hãy tạo gói mới cho sản phẩm khác.",
                            "This package already has assignment history. Changing its product would relabel every "
                            "history row - create a new package instead.",
                            "このパッケージには割当履歴があります。製品を変更すると履歴の表示が変わるため、新しいパッケージを作成してください。",
                        ))

            # Gỡ gói khỏi hạng mục thì cũng gỡ khỏi hợp đồng (contract_id chỉ là bản sao của hạng mục).
            if "contract_line" in data and new_line_id is None and old_line_id:
                data["contract_id"] = None

            if license_id and new_seats is not None:
                used = _open_license_assignments(db, license_id)
                if int(new_seats) < used:
                    raise ValueError(_msg(
                        lang,
                        f"Không thể giảm số bản quyền xuống {new_seats} vì đang có {used} lượt gán chưa thu hồi. Hãy thu hồi bớt trước.",
                        f"Cannot reduce seats to {new_seats}: {used} assignments are still active. Revoke some first.",
                        f"現在 {used} 件が割当中のため、ライセンス数を {new_seats} に減らすことはできません。",
                    ))

            # Gói gắn vào hạng mục hợp đồng: seat của nó được tính là "đã nhận" của hạng mục,
            # nên phải là hạng mục phần mềm và tổng seat không vượt số lượng đặt mua.
            if new_line_id:
                line = db.get(ContractLine, new_line_id)
                if not line or line.is_deleted:
                    raise ValueError(_msg(
                        lang,
                        "Hạng mục hợp đồng được chọn không tồn tại hoặc đã bị xóa.",
                        "The selected contract line does not exist or has been deleted.",
                        "選択された契約明細は存在しないか、削除されています。",
                    ))
                if line.item_kind != ContractItemKind.SOFTWARE:
                    raise ValueError(_msg(
                        lang,
                        "Hạng mục hợp đồng này là phần cứng, không thể gắn gói phần mềm vào.",
                        "This contract line is for hardware; a software package cannot be attached to it.",
                        "この契約明細はハードウェア用のため、ソフトウェアを紐付けることはできません。",
                    ))
                received = line_received_qty(db, line, exclude_license_id=license_id)
                if received + seats_after > line.qty_ordered:
                    raise ValueError(_msg(
                        lang,
                        f"Hạng mục '{line.item_type}' đặt mua {line.qty_ordered}, đã nhận {received}. "
                        f"Gói {seats_after} seats sẽ vượt số lượng đặt mua.",
                        f"Line '{line.item_type}' ordered {line.qty_ordered}, received {received}. "
                        f"A package of {seats_after} seats would exceed the ordered quantity.",
                        f"明細「{line.item_type}」は発注 {line.qty_ordered}、受入済み {received} です。"
                        f"{seats_after} seats を追加すると発注数量を超えます。",
                    ))
                data["contract_id"] = line.contract_id

    async def after_model_change(
        self, data: dict, model: Any, is_created: bool, request: Request
    ) -> None:
        await super().after_model_change(data, model, is_created, request)
        line_ids = {
            getattr(request.state, "itam_prev_license_line_id", None),
            getattr(model, "contract_line_id", None),
        }
        line_ids.discard(None)
        if not line_ids:
            return
        try:
            with SessionLocal() as db:
                _sync_contracts_of_lines(db, line_ids)
                db.commit()
        except Exception:
            logger.exception("Không đồng bộ được tiến độ hợp đồng sau khi lưu gói license #%s", getattr(model, "id", None))

    async def get_object_for_details(self, value: Any) -> Any:
        stmt = self._stmt_by_identifier(value)
        stmt = stmt.options(
            selectinload(License.assignments),
            selectinload(License.contract_line).selectinload(ContractLine.contract),
        )
        for relation in self._details_relations:
            stmt = stmt.options(selectinload(relation))
        return await self._get_object_by_pk(stmt)


def _license_assignment_badge(row: Any) -> Markup:
    lang = get_admin_lang()
    if row.removed_at:
        return Markup(
            f'<span class="badge bg-secondary text-white"><i class="fa-solid fa-ban me-1"></i>{translate("Đã thu hồi", lang)}</span>'
        )
    badge = f'<span class="badge bg-success text-white"><i class="fa-solid fa-circle-check me-1"></i>{translate("Đang sử dụng", lang)}</span>'
    # Hạn riêng của lượt gán ghi đè hạn của gói (trường hợp Trend Micro theo từng máy).
    expiry = row.expiry_date or (row.license.expiry_date if row.license else None)
    if expiry and expiry < today_local():
        badge += (
            f' <span class="badge bg-warning text-dark" title="{expiry.strftime("%d/%m/%Y")}">'
            f'<i class="fa-solid fa-triangle-exclamation me-1"></i>{translate("Gói đã hết hạn", lang)}</span>'
        )
    return Markup(badge)


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
        "status_badge": lambda m, a: _license_assignment_badge(m),
    }
    column_formatters_detail = {
        "license": lambda m, a: (
            f"{m.license.product.name} ({m.license.seats} seats)"
            if (m.license and m.license.product)
            else (str(m.license) if m.license else "-")
        ),
        "status_badge": lambda m, a: _license_assignment_badge(m),
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
        lang = _request_lang(request)
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
        a_at = data.get("assigned_at") or getattr(model, "assigned_at", None)

        _reject_future_date(a_at, lang, "Ngày gán bản quyền", "Assignment date", "割当日")
        # Ngày thu hồi ở tương lai giải phóng seat ngay hôm nay -> gán vượt số lượng.
        _reject_future_date(r_at, lang, "Ngày thu hồi bản quyền", "Removal date", "回収日")

        # `model` còn mang giá trị TRƯỚC khi sửa.
        own_id = None if is_created else getattr(model, "id", None)
        was_open = (not is_created) and getattr(model, "removed_at", None) is None
        old_lid = None if is_created else getattr(model, "license_id", None)
        old_pid = None if is_created else getattr(model, "person_id", None)
        old_aid = None if is_created else getattr(model, "asset_id", None)
        new_pid = _pk_of(person_val) if "person" in data else old_pid
        new_aid = _pk_of(asset_val) if "asset" in data else old_aid

        # Bất biến số 7: dòng lịch sử đã thu hồi không được trỏ sang license / máy / người khác.
        if not is_created and not was_open and (lid != old_lid or new_pid != old_pid or new_aid != old_aid):
            raise ValueError(_msg(
                lang,
                "Lượt gán này đã thu hồi. Không thể đổi bản quyền, thiết bị hoặc nhân viên của một dòng lịch sử.",
                "This assignment was revoked. The license, asset or person of a history row cannot be changed.",
                "この割当は回収済みです。履歴のライセンス・機器・担当者は変更できません。",
            ))

        own_expiry = data.get("expiry_date") if "expiry_date" in data else getattr(model, "expiry_date", None)
        if a_at and own_expiry and own_expiry < a_at:
            raise ValueError(_msg(
                lang,
                "Ngày hết hạn của lượt gán không được trước ngày gán.",
                "The assignment's expiry date cannot be before its assignment date.",
                "割当の有効期限を割当日より前にすることはできません。",
            ))

        # Lượt gán sẽ ở trạng thái MỞ sau khi lưu (tạo mới, mở lại lượt đã thu hồi,
        # hoặc đổi sang license khác) -> đều phải còn seat, không chỉ lúc tạo mới.
        if lid and r_at is None:
            with _get_admin_db(request) as db:
                lic = db.get(License, lid)
                if not lic or lic.is_deleted:
                    raise ValueError(_msg(
                        lang,
                        "Bản quyền được chọn không tồn tại hoặc đã bị xóa.",
                        "The selected license does not exist or has been deleted.",
                        "選択されたライセンスは存在しないか、削除されています。",
                    ))
                if is_created or not was_open or lid != old_lid:
                    active_count = _open_license_assignments(db, lid, exclude_id=own_id)
                    if active_count >= lic.seats:
                        if is_ja:
                            raise ValueError(f"ライセンス '{lic}' の上限（{lic.seats} seats）に達しました。")
                        elif is_en:
                            raise ValueError(f"License '{lic}' has reached maximum seats ({lic.seats}).")
                        else:
                            raise ValueError(f"Bản quyền '{lic}' đã hết lượt gán (tổng {lic.seats} seats).")

                if new_pid and (is_created or not was_open or new_pid != old_pid):
                    _require_active_person(db, new_pid, lang)

                if new_aid and (is_created or not was_open or new_aid != old_aid):
                    asset = db.get(Asset, new_aid)
                    if not asset or asset.is_deleted:
                        raise ValueError(_msg(
                            lang,
                            "Thiết bị được chọn không tồn tại hoặc đã bị xóa.",
                            "The selected asset does not exist or has been deleted.",
                            "選択された機器は存在しないか、削除されています。",
                        ))
                    if asset.status in (AssetStatus.DISPOSED, AssetStatus.LOST):
                        raise ValueError(_msg(
                            lang,
                            f"Không thể gán bản quyền cho thiết bị ở trạng thái '{asset.status.value}' (đã thanh lý / mất).",
                            f"A license cannot be assigned to an asset in status '{asset.status.value}'.",
                            f"ステータスが「{asset.status.value}」の機器にはライセンスを割り当てできません。",
                        ))


class AccessCardAdmin(BaseAdminView, model=AccessCard):
    unique_text_fields = ("card_no",)
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

    async def get_object_for_details(self, value: Any) -> Any:
        # Phải nạp sẵn `loans`: thuộc tính current_borrower đọc quan hệ này sau khi
        # session đã đóng, thiếu nó thì trang chi tiết luôn hiện "Trong kho".
        stmt = self._stmt_by_identifier(value)
        stmt = stmt.options(selectinload(AccessCard.loans).selectinload(CardLoan.person))
        for relation in self._details_relations:
            stmt = stmt.options(selectinload(relation))
        return await self._get_object_by_pk(stmt)

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
        lang = _request_lang(request)
        is_en = (lang == "en")
        is_ja = (lang == "ja")

        card_val = data.get("card")
        cid = getattr(card_val, "id", None)
        if cid is None and str(card_val).isdigit():
            cid = int(card_val)
        if cid is None and hasattr(model, "card_id"):
            cid = model.card_id

        b_at = data.get("borrowed_at") or getattr(model, "borrowed_at", None)
        r_at = data.get("returned_at") if "returned_at" in data else getattr(model, "returned_at", None)

        _reject_future_date(b_at, lang, "Ngày mượn thẻ", "Borrow date", "貸出日")
        # Ngày trả ở tương lai làm thẻ "đã trả" ngay hôm nay nhưng vẫn chặn lượt mượn mới đến ngày đó.
        _reject_future_date(r_at, lang, "Ngày trả thẻ", "Return date", "返却日")

        # `model` còn mang giá trị TRƯỚC khi sửa.
        old_cid = None if is_created else getattr(model, "card_id", None)
        old_pid = None if is_created else getattr(model, "person_id", None)
        was_open = (not is_created) and getattr(model, "returned_at", None) is None
        request.state.itam_prev_card_id = old_cid
        loan_pid = _pk_of(data.get("person")) if "person" in data else old_pid

        # Bất biến số 7: lượt mượn đã trả không được trỏ sang thẻ khác hay người khác.
        if not is_created and not was_open and (cid != old_cid or loan_pid != old_pid):
            raise ValueError(_msg(
                lang,
                "Lượt mượn này đã trả. Không thể đổi thẻ hoặc người mượn của một dòng lịch sử.",
                "This loan is closed. The card or borrower of a history row cannot be changed.",
                "この貸出は返却済みです。履歴のカード・借用者は変更できません。",
            ))

        # Người mượn là nhân viên HOẶC người bên ngoài. Điền cả hai thì màn hình chỉ hiện
        # nhân viên, tên khách bị che mất.
        ext_name = data.get("external_name") if "external_name" in data else getattr(model, "external_name", None)
        if loan_pid and ext_name and str(ext_name).strip():
            raise ValueError(_msg(
                lang,
                "Chỉ chọn nhân viên mượn HOẶC nhập tên người mượn ngoài, không điền cả hai.",
                "Choose an employee OR enter an external borrower, not both.",
                "社員を選択するか外部借用者名を入力するか、どちらか一方のみにしてください。",
            ))

        # Lượt mượn sẽ ở trạng thái MỞ sau khi lưu -> áp cùng luật với loan_card(),
        # kể cả khi mở lại lượt đã trả hoặc đổi sang thẻ khác (không chỉ lúc tạo mới).
        if cid and r_at is None:
            pid = _form_fk(data, "person", model, "person_id") if data.get("person") or "person" not in data else None
            with _get_admin_db(request) as db:
                card = db.get(AccessCard, cid)
                if not card or card.is_deleted:
                    raise ValueError(_msg(
                        lang,
                        "Thẻ được chọn không tồn tại hoặc đã bị xóa.",
                        "The selected card does not exist or has been deleted.",
                        "選択されたカードは存在しないか、削除されています。",
                    ))
                if (is_created or not was_open or cid != old_cid) and card.status in (CardStatus.LOST, CardStatus.DAMAGED):
                    raise ValueError(
                        f"Thẻ '{card.card_no}' đang ở trạng thái {card.status.value}, không thể cho mượn."
                        if not is_en else f"Card '{card.card_no}' is in status {card.status.value}, cannot loan out."
                    )
                if pid and (is_created or not was_open or pid != old_pid):
                    _require_active_person(db, pid, lang)

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
        # Đồng bộ cả thẻ CŨ nếu form đổi sang thẻ khác, nếu không thẻ cũ kẹt ở BORROWED.
        card_ids = {getattr(request.state, "itam_prev_card_id", None), getattr(model, "card_id", None)}
        card_ids.discard(None)
        if not card_ids:
            return
        user_id = request.session.get("user_id")
        client_ip = request.client.host if request.client else None
        try:
            with SessionLocal() as db:
                for card_id in sorted(card_ids):
                    _sync_card_status(db, card_id, user_id, client_ip)
                db.commit()
        except Exception:
            logger.exception("Không đồng bộ được trạng thái thẻ sau khi lưu lượt mượn #%s", getattr(model, "id", None))



class ContractAdmin(BaseAdminView, model=Contract):
    unique_text_fields = ("code",)
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
    # Tiến độ giao hàng được TÍNH từ số đã nhận của các hạng mục (Rule 8), không gõ tay.
    form_excluded_columns = COMMON_EXCLUDED_COLUMNS + ["lines", "delivery_status"]

    async def after_model_change(
        self, data: dict, model: Any, is_created: bool, request: Request
    ) -> None:
        await super().after_model_change(data, model, is_created, request)
        contract_id = getattr(model, "id", None)
        if not contract_id:
            return
        try:
            with SessionLocal() as db:
                sync_contract_delivery_status(db, contract_id)
                db.commit()
        except Exception:
            logger.exception("Không tính lại được tiến độ giao hàng của hợp đồng #%s", contract_id)

    # Thiếu danh sách cột tìm kiếm thì ?search=... không lọc gì cả (liệt kê toàn bộ hợp đồng).
    column_searchable_list = [Contract.code, Contract.vendor_name]

    def list_query(self, request: Request) -> Select:
        stmt = super().list_query(request)
        return stmt.options(
            selectinload(Contract.lines).selectinload(ContractLine.assets),
        )


def _receive_button(line: Any, hardware_label: str, css: str, font_size: str) -> str:
    """Nút nhận hàng của một hạng mục - chỉ hiện với người có quyền nhận loại hàng đó."""
    if not _can_receive_line(line):
        return ""
    return (
        f'<a href="{_receive_url(line)}" class="btn btn-sm {css} py-0 px-2 fw-semibold" style="font-size: {font_size};">'
        f'<i class="fa-solid fa-boxes-packing me-1"></i>{_receive_label(line, hardware_label)}</a>'
    )


def _item_kind_badge(line: Any) -> Markup:
    if line.item_kind == ContractItemKind.SOFTWARE:
        return Markup(
            f'<span class="badge bg-info-subtle text-info border border-info-subtle px-2 py-1">'
            f'<i class="fa-solid fa-compact-disc me-1"></i>{translate("Phần mềm", get_admin_lang())}</span>'
        )
    return Markup(
        f'<span class="badge bg-light text-secondary border px-2 py-1">'
        f'<i class="fa-solid fa-laptop me-1"></i>{translate("Phần cứng", get_admin_lang())}</span>'
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
        ContractLine.item_kind,
        ContractLine.qty_ordered,
        "qty_delivered",
        "qty_remaining",
        "delivery_progress",
    ]
    column_details_list = [
        ContractLine.id,
        ContractLine.contract,
        ContractLine.item_type,
        ContractLine.item_kind,
        ContractLine.spec,
        ContractLine.qty_ordered,
        "qty_delivered",
        "qty_remaining",
        "delivery_progress",
    ] + COMMON_EXCLUDED_COLUMNS
    column_labels = {
        "contract": "Hợp đồng",
        "item_type": "Hạng mục hàng hóa",
        "item_kind": "Loại hạng mục",
        "spec": "Thông số kỹ thuật",
        "qty_ordered": "Số lượng đặt mua",
        "qty_delivered": "Đã nhận",
        "qty_remaining": "Còn lại",
        "delivery_progress": "Tiến độ",
    }
    column_formatters = {
        "item_kind": lambda m, a: _item_kind_badge(m),
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
                    f'{_receive_button(m, "Nhận hàng", "btn-outline-primary", "11px")}'
                )
                if m.qty_delivered > 0
                else Markup(
                    f'<span class="badge bg-light text-secondary border me-2"><i class="fa-regular fa-clock me-1"></i>{translate("Chưa nhận", get_admin_lang())}</span>'
                    f'{_receive_button(m, "Nhận hàng", "btn-outline-primary", "11px")}'
                )
            )
        ),
    }
    column_formatters_detail = {
        "item_kind": lambda m, a: _item_kind_badge(m),
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
                    f'{_receive_button(m, "Nhập kho theo lô", "btn-primary text-white", "12px")}'
                )
                if m.qty_delivered > 0
                else Markup(
                    f'<span class="badge bg-light text-secondary border me-2"><i class="fa-regular fa-clock me-1"></i>{translate("Chưa nhận", get_admin_lang())}</span>'
                    f'{_receive_button(m, "Nhập kho theo lô", "btn-primary text-white", "12px")}'
                )
            )
        ),
    }
    form_excluded_columns = COMMON_EXCLUDED_COLUMNS + ["assets", "licenses"]

    def list_query(self, request: Request) -> Select:
        stmt = super().list_query(request)
        return stmt.options(
            selectinload(ContractLine.contract),
            selectinload(ContractLine.assets),
            selectinload(ContractLine.licenses),
        )

    async def on_model_change(
        self, data: dict, model: Any, is_created: bool, request: Request
    ) -> None:
        await super().on_model_change(data, model, is_created, request)
        new_qty = data.get("qty_ordered")
        line_id = getattr(model, "id", None)
        request.state.itam_prev_contract_id = None if is_created else getattr(model, "contract_id", None)
        if is_created or not line_id:
            return
        lang = _request_lang(request)
        # `model` còn mang loại hạng mục TRƯỚC khi sửa -> số đã nhận tính theo loại hiện tại.
        with _get_admin_db(request) as db:
            received = line_received_qty(db, model)

        new_contract_id = _pk_of(data.get("contract")) if "contract" in data else None
        if new_contract_id is not None and new_contract_id != getattr(model, "contract_id", None) and received > 0:
            raise ValueError(_msg(
                lang,
                "Hạng mục đã có hàng nhận nên không thể chuyển sang hợp đồng khác.",
                "This line already has received items and cannot be moved to another contract.",
                "受入済みの明細は別の契約に移動できません。",
            ))

        new_kind = _enum_of(ContractItemKind, data.get("item_kind")) if "item_kind" in data else None
        if new_kind is not None and new_kind != model.item_kind and received > 0:
            raise ValueError(_msg(
                lang,
                "Không thể đổi loại hạng mục khi hạng mục đã có hàng nhận. Hãy gỡ các thiết bị / gói phần mềm đã nhận trước.",
                "The item kind cannot be changed once something has been received for this line.",
                "受入済みの明細は品目区分を変更できません。",
            ))

        if new_qty is not None and int(new_qty) < received:
            raise ValueError(_msg(
                lang,
                f"Không thể giảm số lượng đặt mua xuống {new_qty} vì hạng mục đã nhận {received}.",
                f"Cannot reduce ordered quantity to {new_qty}: {received} were already received.",
                f"すでに {received} 受領済みのため、発注数量を {new_qty} に減らすことはできません。",
            ))

    async def after_model_change(
        self, data: dict, model: Any, is_created: bool, request: Request
    ) -> None:
        await super().after_model_change(data, model, is_created, request)
        # Thêm hạng mục hoặc đổi số lượng đặt mua làm thay đổi "đã nhận đủ hay chưa".
        contract_ids = {getattr(request.state, "itam_prev_contract_id", None), getattr(model, "contract_id", None)}
        contract_ids.discard(None)
        try:
            with SessionLocal() as db:
                for contract_id in sorted(contract_ids):
                    sync_contract_delivery_status(db, contract_id)
                db.commit()
        except Exception:
            logger.exception("Không đồng bộ được tiến độ hợp đồng sau khi lưu hạng mục #%s", getattr(model, "id", None))

    async def get_object_for_details(self, value: Any) -> Any:
        stmt = self._stmt_by_identifier(value)
        stmt = stmt.options(
            selectinload(ContractLine.contract),
            selectinload(ContractLine.assets),
            selectinload(ContractLine.licenses),
        )
        for relation in self._details_relations:
            stmt = stmt.options(selectinload(relation))
        return await self._get_object_by_pk(stmt)



class PhoneAdmin(BaseAdminView, model=Phone):
    unique_text_fields = ("device_name", "extension_number")
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


def _valid_audit_action(raw: str | None) -> str | None:
    """Giá trị ?action= hợp lệ, hoặc None. Chuỗi lạ đưa thẳng xuống ENUM của PostgreSQL sẽ thành lỗi 500."""
    return raw if raw in {a.value for a in AuditAction} else None


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
    # Các dòng ghi trong cùng một giao dịch có created_at trùng nhau -> thêm id để phân trang ổn định.
    column_default_sort = [(AuditLog.created_at, True), (AuditLog.id, True)]
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
        """Dashboard tổng quan hệ thống ITAM Tokuyama theo triết lý Swiss."""
        from app.core.i18n import get_current_lang, translate

        current_lang = get_current_lang(request)
        today = today_local()
        sixty_days_later = today + dt.timedelta(days=60)

        with SessionLocal() as db:
            # Bảng cảnh báo phải theo đúng ma trận quyền (kể cả quyền ghi đè), không theo tên
            # vai trò: gỡ quyền xem License/Audit của một vai trò thì dashboard cũng phải ẩn.
            user = getattr(request.state, "current_user", None) or get_user_from_request(request, db)

            def _can_view(module: Module) -> bool:
                return bool(user) and has_permission(db, user, module, PermissionAction.VIEW)

            can_view_audit = _can_view(Module.AUDIT)
            can_view_licenses = _can_view(Module.LICENSES)
            can_view_cards = _can_view(Module.CARDS)

            counts_stmt = select(
                select(func.count()).select_from(Asset).where(Asset.is_deleted.is_(False)).scalar_subquery(),
                select(func.count()).select_from(Assignment).where(
                    Assignment.returned_at.is_(None), Assignment.is_deleted.is_(False)
                ).scalar_subquery(),
                select(func.count()).select_from(License).where(License.is_deleted.is_(False)).scalar_subquery(),
                select(func.count()).select_from(AccessCard).where(AccessCard.is_deleted.is_(False)).scalar_subquery(),
                # Nhãn trên dashboard là "Nhân sự đang làm việc": không đếm người đã nghỉ / chưa vào làm.
                select(func.count()).select_from(Person).where(
                    Person.is_deleted.is_(False), Person.status == PersonStatus.ACTIVE
                ).scalar_subquery(),
                select(func.count()).select_from(Contract).where(Contract.is_deleted.is_(False)).scalar_subquery(),
                select(func.count()).select_from(CardLoan).where(
                    CardLoan.returned_at.is_(None), CardLoan.is_deleted.is_(False)
                ).scalar_subquery(),
                # "Trong kho" là máy có trạng thái IN_STOCK, không phải "tổng trừ đang mượn":
                # cách trừ đó tính cả máy đang sửa, đã thanh lý, bị mất là hàng tồn.
                select(func.count()).select_from(Asset).where(
                    Asset.is_deleted.is_(False), Asset.status == AssetStatus.IN_STOCK
                ).scalar_subquery(),
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
                    in_stock_count,
                ) = counts_row
            else:
                asset_count = assignment_count = license_count = card_count = person_count = contract_count = active_card_loans = in_stock_count = 0

            # Audit logs (chỉ query khi có quyền xem)
            recent_logs = []
            if can_view_audit:
                recent_logs = db.scalars(
                    select(AuditLog).options(joinedload(AuditLog.user)).order_by(AuditLog.id.desc()).limit(8)
                ).all()

            # Overdue card loans (FR-17) - chỉ query khi có quyền xem thẻ
            overdue_loans_raw = []
            overdue_loan_count = 0
            if can_view_cards:
                # Số trên huy hiệu là tổng thật; danh sách bên dưới chỉ hiện 8 dòng đầu.
                overdue_loan_count = db.scalar(
                    select(func.count()).select_from(CardLoan).where(
                        CardLoan.returned_at.is_(None),
                        CardLoan.is_deleted.is_(False),
                        CardLoan.expected_return_at.is_not(None),
                        CardLoan.expected_return_at < today,
                    )
                ) or 0
                overdue_loans_raw = db.scalars(
                    select(CardLoan)
                    .options(
                        joinedload(CardLoan.card),
                        joinedload(CardLoan.person),
                    )
                    .where(
                        CardLoan.returned_at.is_(None),
                        CardLoan.is_deleted.is_(False),
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
            expiring_license_count = 0
            expired_license_count = 0
            if can_view_licenses:
                # Hạn hiệu lực của một gói = hạn sớm nhất giữa hạn của gói và hạn riêng của các
                # lượt gán đang mở (Trend Micro ghi hạn theo từng máy, gói không có hạn chung).
                own_expiry_rows = db.execute(
                    select(LicenseAssignment.license_id, func.min(LicenseAssignment.expiry_date))
                    .join(License, License.id == LicenseAssignment.license_id)
                    .where(
                        LicenseAssignment.removed_at.is_(None),
                        LicenseAssignment.is_deleted.is_(False),
                        LicenseAssignment.expiry_date.is_not(None),
                        License.is_deleted.is_(False),
                    )
                    .group_by(LicenseAssignment.license_id)
                ).all()
                own_expiry = {lid: exp for lid, exp in own_expiry_rows}

                package_rows = db.execute(
                    select(License.id, License.expiry_date).where(License.is_deleted.is_(False))
                ).all()
                effective: dict[int, dt.date] = {}
                for lid, package_expiry in package_rows:
                    candidates = [d for d in (package_expiry, own_expiry.get(lid)) if d is not None]
                    if candidates:
                        effective[lid] = min(candidates)
                expired_license_count = sum(1 for d in effective.values() if d < today)
                expiring_license_count = sum(1 for d in effective.values() if today <= d <= sixty_days_later)
                assignment_alert_ids = [
                    lid for lid, d in effective.items()
                    if d <= sixty_days_later and lid in own_expiry and own_expiry[lid] == d
                ]

                expiring_lics_raw = db.scalars(
                    select(License)
                    .options(
                        joinedload(License.product),
                        selectinload(License.assignments),
                    )
                    .where(
                        License.is_deleted.is_(False),
                        or_(
                            License.expiry_date <= sixty_days_later,
                            License.id.in_(assignment_alert_ids),
                        ),
                    )
                    # Sắp hết hạn xếp trước (gần nhất trước), rồi mới đến đã hết hạn (mới nhất
                    # trước). Xếp thuần theo ngày tăng dần thì 8 license hết hạn từ lâu sẽ
                    # chiếm hết bảng và license hết hạn tuần sau không bao giờ hiện ra.
                ).all()

                # Sắp hết hạn xếp trước (gần nhất trước), rồi mới đến đã hết hạn (mới nhất trước),
                # theo hạn hiệu lực; chỉ hiện 8 dòng, số đếm ở trên là tổng thật.
                expiring_lics_raw = sorted(
                    expiring_lics_raw,
                    key=lambda lic: (effective[lic.id] < today, abs((effective[lic.id] - today).days)),
                )[:8]

                for lic in expiring_lics_raw:
                    lic_expiry = effective[lic.id]
                    days_left = (lic_expiry - today).days
                    active_assignments = len([a for a in lic.assignments if a.removed_at is None and not a.is_deleted])
                    product_name = lic.product.name if lic.product else "N/A"
                    expiring_licenses.append({
                        "id": lic.id,
                        "product_name": product_name,
                        "license_type": lic.product.license_type.value if (lic.product and lic.product.license_type) else "",
                        "expiry_date": lic_expiry,
                        "days_left": days_left,
                        "is_expired": days_left < 0,
                        "seats_used": f"{active_assignments}/{lic.seats}",
                        "note": lic.note or "",
                    })

        # Tỷ lệ cấp phát tính trên số máy dùng được (đang mượn + trong kho), không tính máy hỏng / thanh lý / mất.
        usable_assets = assignment_count + in_stock_count
        allocation_rate = int(round((assignment_count / usable_assets) * 100)) if usable_assets > 0 else 0

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
            "in_stock_count": in_stock_count,
            "allocation_rate": allocation_rate,
            "recent_logs": recent_logs,
            "overdue_card_loans": overdue_card_loans,
            "overdue_loan_count": overdue_loan_count,
            "expiring_licenses": expiring_licenses,
            "expiring_license_count": expiring_license_count,
            "expired_license_count": expired_license_count,
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
