"""Router cho tính năng Thùng rác & Khôi phục dữ liệu đã xóa (Recycle Bin & Restore - FR-02/BRD 110 & 210).

Chỉ Admin mới có quyền truy cập module TRASH:
- Xem danh sách các bản ghi đã xóa mềm (is_deleted = True) kèm người xóa, thời điểm xóa và lý do xóa.
- Khôi phục (Restore) an toàn: kiểm tra trước các ràng buộc partial unique index để tránh lỗi duplicate key.
- Ghi audit log với AuditAction.RESTORE.
"""

from __future__ import annotations

import datetime as dt
from typing import Any
from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.admin import get_admin, invalidate_model_count_cache
from app.core.audit import record_audit
from app.core.i18n import get_current_lang, translate
from app.core.permissions import has_permission
from app.core.security import verify_session_token
from app.db import get_db
from app.enums import AuditAction, Module, PermissionAction
from app.models import (
    Asset,
    AssetCategory,
    AssetTag,
    Department,
    Person,
    Role,
    User,
)

router = APIRouter(prefix="/admin/trash", tags=["Recycle Bin"])

ENTITY_MAP: dict[str, Any] = {
    "asset": Asset,
    "person": Person,
    "user": User,
    "department": Department,
    "category": AssetCategory,
    "tag": AssetTag,
    "role": Role,
}


def get_current_admin_actor(
    request: Request, db: Session, action: PermissionAction = PermissionAction.VIEW
) -> User:
    """Xác thực người dùng có quyền trên Thùng rác (Module.TRASH): xem = VIEW, khôi phục = CHANGE."""
    user_id = request.session.get("user_id") if hasattr(request, "session") else None

    if not user_id:
        token = request.cookies.get("itam_session")
        if token:
            payload = verify_session_token(token)
            if payload and "user_id" in payload:
                user_id = payload["user_id"]

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Yêu cầu đăng nhập để truy cập Thùng rác.",
        )

    user = db.scalar(
        select(User).where(
            User.id == int(user_id),
            User.is_active.is_(True),
            User.is_deleted.is_(False),
        )
    )
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Tài khoản không tồn tại hoặc đã bị khóa.",
        )

    # Chỉ Admin mới có quyền truy cập Thùng rác
    if not has_permission(db, user, Module.TRASH, action):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Chỉ Quản trị viên (Admin) mới có quyền truy cập Thùng rác hệ thống.",
        )

    return user


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
async def trash_list_view(
    request: Request,
    entity: str = "all",
    q: str = "",
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Màn hình danh sách bản ghi đã xóa mềm trong Thùng rác."""
    _user = get_current_admin_actor(request, db)
    current_lang = get_current_lang(request)
    admin = get_admin()

    clean_q = q.strip().lower()

    # Truy vấn người dùng để map ID -> Username
    all_users = {u.id: u.username for u in db.scalars(select(User)).all()}

    deleted_items: list[dict[str, Any]] = []

    entities_to_query = [entity] if entity in ENTITY_MAP else list(ENTITY_MAP.keys())

    for ent_key in entities_to_query:
        model_cls = ENTITY_MAP[ent_key]
        if not hasattr(model_cls, "is_deleted"):
            continue

        query = select(model_cls).where(model_cls.is_deleted.is_(True))
        # Khi tìm kiếm phải xét toàn bộ bản ghi đã xóa: lọc sau LIMIT 50 thì không bao giờ
        # tìm ra món đã xóa từ lâu.
        row_limit = 1000 if clean_q else 50
        records = db.scalars(query.order_by(model_cls.deleted_at.desc().nullslast()).limit(row_limit)).all()

        for rec in records:
            display_name = str(rec)
            identifier = ""
            details = ""

            if ent_key == "asset":
                identifier = rec.device_code
                details = f"Model: {rec.model or '—'} | S/N: {rec.serial or '—'}"
            elif ent_key == "person":
                identifier = rec.staff_code or f"#{rec.id}"
                details = f"{rec.full_name} ({rec.email or 'No email'})"
            elif ent_key == "role":
                identifier = rec.code
                details = rec.name_en
            elif ent_key == "user":
                identifier = rec.username
                details = f"{rec.display_name} (@{rec.username})"
            else:
                identifier = f"#{rec.id}"
                details = getattr(rec, "name_en", str(rec))

            # Lọc theo từ khóa tìm kiếm nếu có
            if clean_q:
                combined_text = f"{identifier} {display_name} {details} {rec.delete_reason or ''}".lower()
                if clean_q not in combined_text:
                    continue

            deleter_name = all_users.get(rec.deleted_by, f"User #{rec.deleted_by}") if rec.deleted_by else "—"

            deleted_items.append({
                "entity_type": ent_key,
                "id": rec.id,
                "identifier": identifier,
                "display_name": display_name,
                "details": details,
                "deleted_at": rec.deleted_at,
                "deleter": deleter_name,
                "reason": rec.delete_reason or "—",
            })

    # Sắp xếp theo ngày xóa mới nhất lên trước
    deleted_items.sort(
        key=lambda x: x["deleted_at"] or dt.datetime.min.replace(tzinfo=dt.timezone.utc),
        reverse=True,
    )

    counts: dict[str, int] = {}
    for k, cls in ENTITY_MAP.items():
        if hasattr(cls, "is_deleted"):
            cnt = db.scalar(select(func.count()).select_from(cls).where(cls.is_deleted.is_(True))) or 0
            counts[k] = cnt
    total_in_trash = sum(counts.values())

    context = {
        "request": request,
        "admin": admin,
        "current_lang": current_lang,
        "current_entity": entity,
        "query": clean_q,
        "items": deleted_items,
        "counts": counts,
        "total_in_trash": total_in_trash,
        "title": translate("Thùng rác & Khôi phục", current_lang),
        "subtitle": f"{len(deleted_items)} " + translate("bản ghi đã xóa mềm", current_lang),
    }

    return await admin.templates.TemplateResponse(request, "sqladmin/trash.html", context)


@router.post("/restore")
async def restore_item(
    request: Request,
    entity_type: str = Form(...),
    item_id: int = Form(...),
    db: Session = Depends(get_db),
) -> JSONResponse:
    """Khôi phục bản ghi đã xóa mềm và ghi audit log RESTORE."""
    # Khôi phục là thao tác ghi: quyền chỉ-xem thùng rác không được phép làm sống lại bản ghi.
    user = get_current_admin_actor(request, db, PermissionAction.CHANGE)

    if entity_type not in ENTITY_MAP:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Loại dữ liệu '{entity_type}' không hợp lệ.",
        )

    model_cls = ENTITY_MAP[entity_type]
    rec = db.get(model_cls, item_id)

    if not rec:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bản ghi không tồn tại trong hệ thống.",
        )

    if not rec.is_deleted:
        return JSONResponse({
            "success": True,
            "message": "Bản ghi này hiện đang hoạt động bình thường, không cần khôi phục.",
        })

    # Kiểm tra va chạm Unique Constraints trước khi khôi phục
    conflict_err = check_restore_conflicts(db, entity_type, rec)
    if conflict_err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=conflict_err,
        )

    old_reason = rec.delete_reason
    old_deleted_at = rec.deleted_at

    # Lưới an toàn cho các partial unique index chưa được kiểm tra tường minh ở trên:
    # trả 400 có thông báo thay vì để IntegrityError thành lỗi 500.
    try:
        # Thực hiện khôi phục
        rec.is_deleted = False
        rec.deleted_at = None
        rec.deleted_by = None
        rec.delete_reason = None
        rec.updated_at = dt.datetime.now(dt.timezone.utc)
        rec.updated_by = user.id

        # Ghi nhận Audit Log RESTORE
        client_ip = request.client.host if request.client else None
        record_audit(
            db,
            action=AuditAction.RESTORE,
            table_name=model_cls.__tablename__,
            record_id=rec.id,
            user_id=user.id,
            before={"is_deleted": True, "delete_reason": old_reason, "deleted_at": str(old_deleted_at)},
            after={"is_deleted": False},
            ip_address=client_ip,
        )

        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Không thể khôi phục: dữ liệu của bản ghi này trùng với một bản ghi đang hoạt động.",
        )
    invalidate_model_count_cache(model_cls)

    return JSONResponse({
        "success": True,
        "message": f"Khôi phục thành công bản ghi #{rec.id} ({model_cls.__name__}).",
    })


def check_restore_conflicts(db: Session, entity_type: str, rec: Any) -> str | None:
    """Kiểm tra xem bản ghi có bị xung đột partial unique index với bản ghi đang sống nào không."""
    if entity_type == "asset":
        # Check Serial
        if rec.serial:
            dup_serial = db.scalar(
                select(Asset).where(
                    Asset.id != rec.id,
                    func.lower(Asset.serial) == rec.serial.lower(),
                    Asset.is_deleted.is_(False),
                )
            )
            if dup_serial:
                return f"Không thể khôi phục: Serial '{rec.serial}' hiện đã được sử dụng bởi thiết bị #{dup_serial.id} ({dup_serial.device_code})."

        if rec.device_code:
            dup_vendor = db.scalar(
                select(Asset).where(
                    Asset.id != rec.id,
                    func.lower(Asset.device_code) == rec.device_code.lower(),
                    Asset.is_deleted.is_(False),
                )
            )
            if dup_vendor:
                return f"Không thể khôi phục: Mã thiết bị '{rec.device_code}' hiện đã được sử dụng bởi thiết bị #{dup_vendor.id}."

    elif entity_type == "person":
        # Check Staff code
        dup_staff = rec.staff_code and db.scalar(
            select(Person).where(
                Person.id != rec.id,
                func.lower(Person.staff_code) == rec.staff_code.lower(),
                Person.is_deleted.is_(False),
            )
        )
        if dup_staff:
            return f"Không thể khôi phục: Mã nhân viên '{rec.staff_code}' đã tồn tại ở nhân sự #{dup_staff.id} ({dup_staff.full_name})."

        # Check User ID
        if rec.user_id:
            dup_uid = db.scalar(
                select(Person).where(
                    Person.id != rec.id,
                    func.lower(Person.user_id) == rec.user_id.lower(),
                    Person.is_deleted.is_(False),
                )
            )
            if dup_uid:
                return f"Không thể khôi phục: UserID '{rec.user_id}' đã thuộc về nhân sự #{dup_uid.id}."

        if rec.email:
            dup_email = db.scalar(
                select(Person).where(
                    Person.id != rec.id,
                    func.lower(Person.email) == rec.email.lower(),
                    Person.is_deleted.is_(False),
                )
            )
            if dup_email:
                return f"Không thể khôi phục: Email '{rec.email}' đã thuộc về nhân sự #{dup_email.id} ({dup_email.full_name})."

    elif entity_type == "user":
        dup_user = db.scalar(
            select(User).where(
                User.id != rec.id,
                func.lower(User.username) == rec.username.lower(),
                User.is_deleted.is_(False),
            )
        )
        if dup_user:
            return f"Không thể khôi phục: Tên đăng nhập '{rec.username}' đã thuộc về người dùng #{dup_user.id}."

    return None
