"""Router xác thực đăng nhập / đăng xuất cho hệ thống ITAM."""

from __future__ import annotations

import datetime as dt
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import audit_login
from app.core.permissions import get_user_permissions
from app.core.reveal import RevealGate
from app.core.security import DUMMY_PASSWORD_HASH, create_session_token, verify_password, verify_session_token
from app.db import get_db
from app.models import User

router = APIRouter(prefix="/auth", tags=["Authentication"])

# Cổng reveal chia sẻ cho toàn ứng dụng
reveal_gate = RevealGate()


class LoginInput(BaseModel):
    username: str
    password: str


class UserResponse(BaseModel):
    id: int
    username: str
    display_name: str
    role: str
    preferred_lang: str


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
) -> User:
    """Dependency trích xuất user hiện tại từ cookie itam_session hoặc header."""
    token = request.cookies.get("itam_session")
    if not token and "authorization" in request.headers:
        auth_header = request.headers["authorization"]
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Chưa đăng nhập hoặc phiên làm việc đã hết hạn.",
        )

    payload = verify_session_token(token)
    if not payload or "user_id" not in payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Phiên làm việc không hợp lệ.",
        )

    user = db.scalar(
        select(User).where(
            User.id == payload["user_id"],
            User.is_active.is_(True),
            User.is_deleted.is_(False),
        )
    )
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Tài khoản không tồn tại hoặc đã bị vô hiệu hoá.",
        )
    return user


@router.post("/login")
def login(
    data: LoginInput,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    """Đăng nhập hệ thống, kiểm tra mật khẩu bằng Argon2id và ghi nhận audit log."""
    client_ip = request.client.host if request.client else None
    username = data.username.strip()

    user = db.scalar(
        select(User).where(
            User.username == username,
            User.is_active.is_(True),
            User.is_deleted.is_(False),
        )
    )

    valid_password = False
    if user:
        valid_password = verify_password(data.password, user.password_hash)
    else:
        verify_password(data.password, DUMMY_PASSWORD_HASH)

    if not user or not valid_password:
        audit_login(db, user_id=user.id if user else None, success=False, username=username, ip_address=client_ip)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Tên đăng nhập hoặc mật khẩu không chính xác.",
        )

    # Đăng nhập thành công
    user.last_login_at = dt.datetime.now(dt.timezone.utc)
    audit_login(db, user_id=user.id, success=True, username=username, ip_address=client_ip)
    db.commit()

    token = create_session_token({
        "user_id": user.id,
        "username": user.username,
        "role": user.role.code,
    })

    # Thiết lập cookie bảo mật
    response.set_cookie(
        key="itam_session",
        value=token,
        httponly=True,
        samesite="lax",
        max_age=1800,  # 30 phút
    )

    return {
        "status": "ok",
        "token": token,
        "user": {
            "id": user.id,
            "username": user.username,
            "display_name": user.display_name,
            "role": user.role.code,
            "preferred_lang": user.preferred_lang,
        },
    }


@router.post("/logout")
def logout(
    response: Response,
    request: Request,
    db: Session = Depends(get_db),
):
    """Đăng xuất, xoá cookie phiên và thu hồi reveal token nếu có."""
    token = request.cookies.get("itam_session")
    if token:
        payload = verify_session_token(token)
        if payload and "user_id" in payload:
            reveal_gate.revoke(payload["user_id"])

    response.delete_cookie("itam_session")
    return {"status": "ok", "message": "Đã đăng xuất thành công."}


@router.get("/me")
def get_me(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    """Lấy thông tin người dùng hiện tại và ma trận quyền hiệu lực."""
    perms = get_user_permissions(db, current_user)
    return {
        "id": current_user.id,
        "username": current_user.username,
        "display_name": current_user.display_name,
        "role": current_user.role.code,
        "preferred_lang": current_user.preferred_lang,
        "permissions": [f"{mod}:{act}" for mod, act in sorted(perms)],
    }
