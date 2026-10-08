"""Dịch vụ nghiệp vụ Quản lý Danh bạ & Thiết bị Thoại (Phase 5 - FR-15)."""

from __future__ import annotations

import datetime as dt
from typing import Any
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.audit import record_audit
from app.enums import AuditAction, PhoneDeviceType
from app.models import Phone


def list_phones(
    db: Session,
    active_only: bool = False,
    search: str | None = None,
) -> list[Phone]:
    """Lấy danh sách máy điện thoại và số nội bộ."""
    query = (
        select(Phone)
        .options(selectinload(Phone.location))
        .where(Phone.is_deleted.is_(False))
    )

    if active_only:
        query = query.where(Phone.is_active.is_(True))

    if search and search.strip():
        term = f"%{search.strip()}%"
        query = query.where(
            or_(
                Phone.device_name.ilike(term),
                Phone.extension_number.ilike(term),
                Phone.remarks.ilike(term),
            )
        )

    query = query.order_by(Phone.extension_number.asc().nulls_last(), Phone.device_name.asc())
    return list(db.scalars(query).all())


def create_phone(
    db: Session,
    device_name: str,
    device_type: PhoneDeviceType | str,
    extension_number: str | None = None,
    location_id: int | None = None,
    is_active: bool = True,
    remarks: str | None = None,
    user_id: int | None = None,
) -> Phone:
    """Tạo mới thiết bị thoại trong danh bạ."""
    clean_name = device_name.strip()
    if not clean_name:
        raise ValueError("Tên máy điện thoại không được để trống")

    clean_ext = extension_number.strip() if extension_number and extension_number.strip() else None
    if clean_ext == "N/A":
        clean_ext = None  # Quy ước DB: không lưu chữ 'N/A' mà để NULL

    # Kiểm tra trùng device_name
    dup_name = db.scalar(
        select(Phone).where(
            Phone.device_name == clean_name,
            Phone.is_deleted.is_(False),
        )
    )
    if dup_name:
        raise ValueError(f"Tên máy điện thoại '{clean_name}' đã tồn tại")

    # Kiểm tra trùng extension_number nếu có
    if clean_ext:
        dup_ext = db.scalar(
            select(Phone).where(
                Phone.extension_number == clean_ext,
                Phone.is_deleted.is_(False),
            )
        )
        if dup_ext:
            raise ValueError(f"Số máy nhánh '{clean_ext}' đã được sử dụng")

    dtype_enum = (
        device_type
        if isinstance(device_type, PhoneDeviceType)
        else PhoneDeviceType(str(device_type))
    )

    phone = Phone(
        device_name=clean_name,
        device_type=dtype_enum,
        extension_number=clean_ext,
        location_id=location_id,
        is_active=is_active,
        remarks=remarks,
    )
    db.add(phone)
    db.flush()

    record_audit(
        db=db,
        action=AuditAction.CREATE,
        table_name="phones",
        record_id=phone.id,
        user_id=user_id,
        after={
            "device_name": phone.device_name,
            "device_type": phone.device_type.value,
            "extension_number": phone.extension_number,
            "location_id": phone.location_id,
            "is_active": phone.is_active,
        },
    )

    return phone


def update_phone(
    db: Session,
    phone_id: int,
    device_name: str | None = None,
    device_type: PhoneDeviceType | str | None = None,
    extension_number: str | None = None,
    location_id: int | None = None,
    is_active: bool | None = None,
    remarks: str | None = None,
    user_id: int | None = None,
) -> Phone:
    """Cập nhật thông tin thiết bị thoại."""
    phone = db.get(Phone, phone_id)
    if not phone or phone.is_deleted:
        raise ValueError(f"Thiết bị thoại ID {phone_id} không tồn tại hoặc đã bị xoá")

    before_state: dict[str, Any] = {
        "device_name": phone.device_name,
        "device_type": phone.device_type.value,
        "extension_number": phone.extension_number,
        "location_id": phone.location_id,
        "is_active": phone.is_active,
        "remarks": phone.remarks,
    }

    if device_name is not None:
        clean_name = device_name.strip()
        if not clean_name:
            raise ValueError("Tên máy điện thoại không được để trống")
        if clean_name != phone.device_name:
            dup = db.scalar(
                select(Phone).where(
                    Phone.device_name == clean_name,
                    Phone.id != phone_id,
                    Phone.is_deleted.is_(False),
                )
            )
            if dup:
                raise ValueError(f"Tên máy điện thoại '{clean_name}' đã tồn tại")
            phone.device_name = clean_name

    if extension_number is not None:
        clean_ext = extension_number.strip() if extension_number.strip() else None
        if clean_ext == "N/A":
            clean_ext = None
        if clean_ext != phone.extension_number:
            if clean_ext:
                dup = db.scalar(
                    select(Phone).where(
                        Phone.extension_number == clean_ext,
                        Phone.id != phone_id,
                        Phone.is_deleted.is_(False),
                    )
                )
                if dup:
                    raise ValueError(f"Số máy nhánh '{clean_ext}' đã được sử dụng")
            phone.extension_number = clean_ext

    if device_type is not None:
        phone.device_type = (
            device_type
            if isinstance(device_type, PhoneDeviceType)
            else PhoneDeviceType(str(device_type))
        )

    if location_id is not None:
        phone.location_id = location_id

    if is_active is not None:
        phone.is_active = is_active

    if remarks is not None:
        phone.remarks = remarks

    db.flush()

    after_state: dict[str, Any] = {
        "device_name": phone.device_name,
        "device_type": phone.device_type.value,
        "extension_number": phone.extension_number,
        "location_id": phone.location_id,
        "is_active": phone.is_active,
        "remarks": phone.remarks,
    }

    record_audit(
        db=db,
        action=AuditAction.UPDATE,
        table_name="phones",
        record_id=phone.id,
        user_id=user_id,
        before=before_state,
        after=after_state,
    )

    return phone


def delete_phone(
    db: Session,
    phone_id: int,
    delete_reason: str,
    user_id: int | None = None,
) -> Phone:
    """Xoá mềm thiết bị thoại (bắt buộc có lý do)."""
    clean_reason = delete_reason.strip() if delete_reason else ""
    if not clean_reason:
        raise ValueError("Bắt buộc phải có lý do khi xoá thiết bị thoại")

    phone = db.get(Phone, phone_id)
    if not phone or phone.is_deleted:
        raise ValueError(f"Thiết bị thoại ID {phone_id} không tồn tại hoặc đã bị xoá")

    phone.is_deleted = True
    phone.deleted_at = dt.datetime.now(dt.timezone.utc)
    phone.delete_reason = clean_reason
    phone.is_active = False

    db.flush()

    record_audit(
        db=db,
        action=AuditAction.DELETE,
        table_name="phones",
        record_id=phone.id,
        user_id=user_id,
        extra={"delete_reason": clean_reason},
    )

    return phone
