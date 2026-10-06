"""Ghi Audit Log theo tiêu chuẩn bảo mật GEMINI.md.

Quy tắc bất biến:
- Ghi một dòng cho: CREATE, UPDATE, DELETE, RESTORE, LOGIN, LOGIN_FAIL, REVEAL.
- `before_after` KHÔNG BAO GIỜ được chứa giá trị của các cột trong REDACTED_FIELDS
  (pc_password_enc, email_password_enc, license_key_enc, password_hash).
- Phải lọc triệt để trước khi ghi vào database, không lọc khi hiển thị.
- AuditLog trong DB chỉ INSERT và SELECT, có trigger DB chặn UPDATE và DELETE.
"""

from __future__ import annotations

import datetime as dt
from enum import Enum
import ipaddress
from typing import Any
from sqlalchemy.orm import Session

from app.enums import AuditAction
from app.models import AuditLog, REDACTED_FIELDS


def sanitize_dict(data: dict[str, Any] | None) -> dict[str, Any] | None:
    """Loại bỏ triệt để các trường nhạy cảm trong REDACTED_FIELDS và chuẩn hoá kiểu dữ liệu cho JSONB."""
    if data is None:
        return None

    cleaned: dict[str, Any] = {}
    for key, value in data.items():
        k_lower = key.lower()
        if key in REDACTED_FIELDS or k_lower in REDACTED_FIELDS or k_lower.endswith("_enc") or "password" in k_lower:
            cleaned[key] = "[REDACTED]"
            continue

        # Chuẩn hoá các kiểu không trực tiếp dump JSON
        if isinstance(value, (dt.datetime, dt.date, dt.time)):
            cleaned[key] = value.isoformat()
        elif isinstance(value, Enum):
            cleaned[key] = value.value
        elif isinstance(value, bytes):
            cleaned[key] = "[BINARY]"
        elif isinstance(value, dict):
            cleaned[key] = sanitize_dict(value)
        elif isinstance(value, list):
            cleaned[key] = [
                sanitize_dict(item) if isinstance(item, dict)
                else (item.isoformat() if isinstance(item, (dt.datetime, dt.date)) else item)
                for item in value
            ]
        else:
            cleaned[key] = value

    return cleaned


def _validate_inet(ip: str | None) -> str | None:
    """Kiểm tra tính hợp lệ của địa chỉ IP trước khi lưu vào cột INET PostgreSQL."""
    if not ip:
        return None
    try:
        ipaddress.ip_address(ip)
        return ip
    except ValueError:
        return None


def record_audit(
    db: Session,
    action: AuditAction | str,
    table_name: str,
    record_id: int | None = None,
    user_id: int | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    ip_address: str | None = None,
    extra: dict[str, Any] | None = None,
) -> AuditLog:
    """Tạo một bản ghi audit log với dữ liệu đã được làm sạch bảo mật."""
    act_enum = action if isinstance(action, AuditAction) else AuditAction(str(action))

    before_after_payload: dict[str, Any] = {}
    if before is not None:
        before_after_payload["before"] = sanitize_dict(before)
    if after is not None:
        before_after_payload["after"] = sanitize_dict(after)
    if extra:
        before_after_payload["extra"] = sanitize_dict(extra)

    # Nếu rỗng hoàn toàn thì lưu None
    payload_to_store = before_after_payload if before_after_payload else None

    valid_ip = _validate_inet(ip_address)

    log = AuditLog(
        user_id=user_id,
        table_name=table_name,
        record_id=record_id,
        action=act_enum,
        before_after=payload_to_store,
        ip_address=valid_ip,
    )
    db.add(log)
    db.flush()
    return log


def audit_login(
    db: Session,
    user_id: int | None,
    success: bool,
    ip_address: str | None = None,
    username: str | None = None,
) -> AuditLog:
    """Ghi log sự kiện đăng nhập thành công hoặc thất bại."""
    action = AuditAction.LOGIN if success else AuditAction.LOGIN_FAIL
    extra = {"username": username} if username else None
    return record_audit(
        db=db,
        action=action,
        table_name="users",
        record_id=user_id,
        user_id=user_id,
        ip_address=ip_address,
        extra=extra,
    )


def audit_reveal(
    db: Session,
    user_id: int,
    table_name: str,
    record_id: int,
    field_name: str,
    ip_address: str | None = None,
) -> AuditLog:
    """Ghi log mỗi lần giải mã mật khẩu nhân viên / license key thành công."""
    return record_audit(
        db=db,
        action=AuditAction.REVEAL,
        table_name=table_name,
        record_id=record_id,
        user_id=user_id,
        ip_address=ip_address,
        extra={"revealed_field": field_name},
    )
