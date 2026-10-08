"""API endpoints cho tính năng Ma trận Quyền Vai trò trực quan."""

from __future__ import annotations

from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.permissions import (
    reset_role_permissions_matrix,
    save_role_permissions_matrix,
)
from app.core.security import verify_session_token
from app.db import get_db

router = APIRouter(prefix="/admin/role-permission/matrix", tags=["Role Permission Matrix"])


def _verify_admin_access(request: Request) -> int:
    """Xác thực người dùng hiện tại có vai trò ADMIN hay không."""
    user_id = request.session.get("user_id") if hasattr(request, "session") else None
    role = request.session.get("role") if hasattr(request, "session") else None

    if not user_id:
        token = request.cookies.get("itam_session")
        if token:
            payload = verify_session_token(token)
            if payload:
                user_id = payload.get("user_id")
                role = payload.get("role")

    if not user_id or str(role).upper() != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Chỉ Quản trị viên (ADMIN) mới có quyền thay đổi ma trận quyền hệ thống.",
        )
    return int(user_id)


@router.post("/save")
async def save_role_matrix(request: Request, db: Session = Depends(get_db)) -> JSONResponse:
    """Lưu toàn bộ thay đổi ma trận quyền của một vai trò."""
    admin_id = _verify_admin_access(request)
    try:
        body: dict[str, Any] = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Dữ liệu JSON không hợp lệ.")

    role_id = body.get("role_id")
    if not role_id:
        raise HTTPException(status_code=400, detail="Thiếu mã vai trò (role_id).")

    permissions = body.get("permissions", [])
    client_ip = request.client.host if request.client else None

    try:
        result = save_role_permissions_matrix(
            db=db,
            role_id=int(role_id),
            new_perms=permissions,
            user_id=admin_id,
            ip_address=client_ip,
        )
        return JSONResponse(content=result)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/reset")
async def reset_role_matrix(request: Request, db: Session = Depends(get_db)) -> JSONResponse:
    """Khôi phục ma trận quyền về giá trị mặc định chuẩn của GEMINI.md."""
    admin_id = _verify_admin_access(request)
    try:
        body: dict[str, Any] = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Dữ liệu JSON không hợp lệ.")

    role_id = body.get("role_id")
    if not role_id:
        raise HTTPException(status_code=400, detail="Thiếu mã vai trò (role_id).")

    client_ip = request.client.host if request.client else None

    try:
        result = reset_role_permissions_matrix(
            db=db,
            role_id=int(role_id),
            user_id=admin_id,
            ip_address=client_ip,
        )
        return JSONResponse(content=result)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
