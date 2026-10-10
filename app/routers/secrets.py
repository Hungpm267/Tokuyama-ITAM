"""Router cho tính năng Quản lý và Giải mã Mật khẩu Nhân sự (FR-06)."""

from __future__ import annotations

from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import audit_reveal, record_audit
from app.core.crypto import SecretBox
from app.core.inputs import read_json_object, require_positive_int
from app.core.permissions import has_permission
from app.core.reveal import RevealDenied
from app.core.security import verify_password, verify_session_token
from app.db import get_db
from app.enums import AuditAction, Module, PermissionAction
from app.models import Person, PersonSecret, User
from app.routers.auth import reveal_gate

router = APIRouter(tags=["Person Secrets"])


def get_current_actor(request: Request, db: Session) -> User:
    """Xác thực người dùng từ session hoặc cookie itam_session."""
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
            detail="Yêu cầu đăng nhập để thực hiện thao tác.",
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
    return user


@router.post("/admin/person-secret/save")
async def save_person_secret(
    request: Request,
    db: Session = Depends(get_db),
) -> JSONResponse:
    """Lưu hoặc cập nhật mật khẩu PC/Email đã mã hóa AES-256-GCM cho nhân viên."""
    user = get_current_actor(request, db)

    # Kiểm tra quyền: phải có quyền change hoặc add trên module secrets
    can_change = has_permission(db, user, Module.SECRETS, PermissionAction.CHANGE)
    can_add = has_permission(db, user, Module.SECRETS, PermissionAction.ADD)
    if not (can_change or can_add):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bạn không có quyền quản lý mật khẩu nhân sự.",
        )

    body = await read_json_object(request)
    # Kiểm kiểu chặt: `true` hay "abc" không được bị ép thành nhân sự #1 hoặc gây lỗi 500.
    person_id = require_positive_int(body.get("person_id"), "Thiếu mã nhân sự (person_id).")

    person = db.scalar(
        select(Person).where(
            Person.id == person_id,
            Person.is_deleted.is_(False),
        )
    )
    if not person:
        raise HTTPException(status_code=404, detail="Không tìm thấy hồ sơ nhân sự.")

    box = SecretBox.from_env()

    secret = db.scalar(select(PersonSecret).where(PersonSecret.person_id == person.id))
    is_new = False
    if not secret:
        secret = PersonSecret(person_id=person.id)
        db.add(secret)
        is_new = True

    # 1. Xử lý Mật khẩu PC
    clear_pc = bool(body.get("clear_pc_password"))
    pc_password = body.get("pc_password")
    pc_note = body.get("pc_password_note")

    if clear_pc:
        secret.pc_password_enc = None
        secret.pc_password_note = None
    elif pc_password and str(pc_password).strip():
        aad = SecretBox.aad("person_secrets", person.id, "pc_password_enc")
        secret.pc_password_enc = box.encrypt(str(pc_password).strip(), aad)
        secret.pc_password_note = str(pc_note).strip() if pc_note else None
    elif pc_note is not None:
        secret.pc_password_note = str(pc_note).strip() if pc_note else None

    # 2. Xử lý Mật khẩu Email
    clear_email = bool(body.get("clear_email_password"))
    email_password = body.get("email_password")
    email_note = body.get("email_password_note")

    if clear_email:
        secret.email_password_enc = None
        secret.email_password_note = None
    elif email_password and str(email_password).strip():
        aad = SecretBox.aad("person_secrets", person.id, "email_password_enc")
        secret.email_password_enc = box.encrypt(str(email_password).strip(), aad)
        secret.email_password_note = str(email_note).strip() if email_note else None
    elif email_note is not None:
        secret.email_password_note = str(email_note).strip() if email_note else None

    secret.updated_by = user.id
    secret.key_version = box.current_version

    # Ghi audit log (CREATE hoặc UPDATE) - mã hoá & mật khẩu được tự động redacted
    client_ip = request.client.host if request.client else None
    record_audit(
        db=db,
        action=AuditAction.CREATE if is_new else AuditAction.UPDATE,
        table_name="person_secrets",
        record_id=person.id,
        user_id=user.id,
        ip_address=client_ip,
        extra={
            "staff_code": person.staff_code,
            "has_pc_password": secret.pc_password_enc is not None,
            "has_email_password": secret.email_password_enc is not None,
        },
    )

    db.commit()

    return JSONResponse(
        content={
            "success": True,
            "message": "Cập nhật mật khẩu nhân sự thành công.",
            "has_pc_password": secret.pc_password_enc is not None,
            "has_email_password": secret.email_password_enc is not None,
        }
    )


async def _handle_reveal(
    request: Request,
    person_id: int,
    db: Session,
) -> JSONResponse:
    """Xử lý yêu cầu giải mã mật khẩu với xác thực Admin 2 lớp theo chuẩn FR-06."""
    user = get_current_actor(request, db)

    # Kiểm tra quyền: bắt buộc phải có quyền view trên module secrets
    if not has_permission(db, user, Module.SECRETS, PermissionAction.VIEW):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bạn không có quyền xem mật khẩu nhân sự.",
        )

    try:
        body: dict[str, Any] = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Dữ liệu JSON không hợp lệ.")

    field_name = body.get("field", "pc_password")
    if field_name not in ("pc_password", "email_password"):
        raise HTTPException(
            status_code=400,
            detail="Trường yêu cầu không hợp lệ (phải là pc_password hoặc email_password).",
        )

    admin_password = body.get("admin_password")
    reveal_token = body.get("reveal_token")

    # Xác thực mật khẩu admin hoặc reveal token hợp lệ
    active_token: str | None = None
    if admin_password:
        try:
            active_token = reveal_gate.authorize(
                user_id=user.id,
                password=str(admin_password),
                password_hash=user.password_hash,
                verifier=verify_password,
            )
        except RevealDenied as exc:
            if exc.reason == "locked":
                return JSONResponse(
                    status_code=status.HTTP_423_LOCKED,
                    content={
                        "success": False,
                        "error": "Tài khoản bị tạm khóa chức năng xem mật khẩu 15 phút do nhập sai quá 5 lần.",
                        "reason": "locked",
                    },
                )
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={
                    "success": False,
                    "error": "Mật khẩu quản trị viên không chính xác.",
                    "reason": "bad_password",
                },
            )
    elif reveal_token:
        try:
            reveal_gate.check_token(user.id, str(reveal_token))
            active_token = str(reveal_token)
        except RevealDenied as exc:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={
                    "success": False,
                    "error": "Phiên xác thực đã hết hạn hoặc không hợp lệ. Vui lòng nhập lại mật khẩu.",
                    "need_reauth": True,
                    "reason": exc.reason,
                },
            )
    else:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={
                "success": False,
                "error": "Vui lòng nhập mật khẩu Quản trị viên để xác thực.",
                "need_reauth": True,
                "reason": "no_token",
            },
        )

    # Tìm bản ghi person_secret
    secret = db.scalar(
        select(PersonSecret).where(PersonSecret.person_id == int(person_id))
    )
    if not secret:
        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "value": None,
                "note": None,
                "message": "Chưa thiết lập mật khẩu.",
                "reveal_token": active_token,
                "auto_hide_seconds": 60,
            },
        )

    enc_attr = f"{field_name}_enc"
    enc_bytes = getattr(secret, enc_attr, None)
    if not enc_bytes:
        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "value": None,
                "note": getattr(secret, f"{field_name}_note", None),
                "message": "Chưa thiết lập mật khẩu.",
                "reveal_token": active_token,
                "auto_hide_seconds": 60,
            },
        )

    # Giải mã AES-256-GCM
    box = SecretBox.from_env()
    aad = SecretBox.aad("person_secrets", secret.person_id, enc_attr)
    plaintext = box.decrypt(enc_bytes, aad)

    # Ghi nhận Audit Log (action = REVEAL)
    client_ip = request.client.host if request.client else None
    audit_reveal(
        db=db,
        user_id=user.id,
        table_name="person_secrets",
        record_id=secret.person_id,
        field_name=field_name,
        ip_address=client_ip,
    )
    db.commit()

    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "value": plaintext,
            "note": getattr(secret, f"{field_name}_note", None),
            "field": field_name,
            "reveal_token": active_token,
            "auto_hide_seconds": 60,
        },
    )


@router.post("/persons/{person_id}/secrets/reveal")
async def reveal_person_secret_canonical(
    person_id: int,
    request: Request,
    db: Session = Depends(get_db),
) -> JSONResponse:
    """Endpoint chính thức xem mật khẩu theo chuẩn BRD FR-06."""
    return await _handle_reveal(request, person_id, db)


@router.post("/admin/person-secret/{person_id}/reveal")
async def reveal_person_secret_admin_alias(
    person_id: int,
    request: Request,
    db: Session = Depends(get_db),
) -> JSONResponse:
    """Alias cho giao diện quản trị SQLAdmin."""
    return await _handle_reveal(request, person_id, db)


@router.post("/admin/person-secret/reveal/revoke")
async def revoke_reveal_token(
    request: Request,
    db: Session = Depends(get_db),
) -> JSONResponse:
    """Thu hồi token xác thực xem mật khẩu khi người dùng bấm ẩn hoặc đăng xuất."""
    user = get_current_actor(request, db)
    reveal_gate.revoke(user.id)
    return JSONResponse(
        content={
            "success": True,
            "message": "Đã thu hồi token xác thực xem mật khẩu.",
        }
    )
