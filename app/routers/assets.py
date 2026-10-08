"""Router API cho các thao tác Quản lý Tài sản & Bàn giao mượn–trả (FR-07, FR-10)."""

from __future__ import annotations

import datetime as dt
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.permissions import has_permission
from app.core.security import verify_session_token
from app.db import get_db
from app.enums import AssetStatus, Module, PermissionAction, PersonStatus
from app.models import Person, User
from app.services.assignment_service import (
    assign_asset,
    get_asset_assignment_history,
    return_asset,
)

router = APIRouter(prefix="/admin", tags=["Assets & Assignments"])


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


@router.get("/api/persons/search")
def search_active_persons(
    request: Request,
    q: str = "",
    db: Session = Depends(get_db),
) -> JSONResponse:
    """Tìm kiếm nhanh nhân sự đang làm việc (dành cho modal bàn giao máy)."""
    user = get_current_actor(request, db)
    if not has_permission(db, user, Module.PERSONS, PermissionAction.VIEW):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bạn không có quyền xem thông tin nhân sự.",
        )

    clean_q = q.strip()
    stmt = (
        select(Person)
        .options(selectinload(Person.department))
        .where(Person.is_deleted.is_(False), Person.status == PersonStatus.ACTIVE)
    )
    if clean_q:
        pattern = f"%{clean_q}%"
        stmt = stmt.where(
            or_(
                Person.full_name.ilike(pattern),
                Person.staff_code.ilike(pattern),
                Person.email.ilike(pattern),
            )
        )
    stmt = stmt.order_by(Person.full_name.asc()).limit(20)
    persons = db.scalars(stmt).all()

    return JSONResponse(
        content=[
            {
                "id": p.id,
                "staff_code": p.staff_code,
                "full_name": p.full_name,
                "department": p.department.name_en if p.department else "",
                "email": p.email or "",
            }
            for p in persons
        ]
    )


@router.post("/assets/{asset_id}/assign")
async def api_assign_asset(
    asset_id: int,
    request: Request,
    db: Session = Depends(get_db),
) -> JSONResponse:
    """Bàn giao thiết bị cho nhân viên (Assign)."""
    user = get_current_actor(request, db)
    if not (
        has_permission(db, user, Module.ASSETS, PermissionAction.CHANGE)
        or has_permission(db, user, Module.ASSETS, PermissionAction.ADD)
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bạn không có quyền bàn giao thiết bị.",
        )

    try:
        body: dict[str, Any] = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Dữ liệu JSON không hợp lệ.")

    person_id = body.get("person_id")
    if not person_id:
        raise HTTPException(status_code=400, detail="Vui lòng chọn nhân viên nhận máy.")

    borrowed_at_raw = body.get("borrowed_at")
    if borrowed_at_raw:
        try:
            borrowed_at = dt.date.fromisoformat(str(borrowed_at_raw).strip())
        except ValueError:
            raise HTTPException(status_code=400, detail="Định dạng ngày bàn giao không hợp lệ (YYYY-MM-DD).")
    else:
        borrowed_at = dt.date.today()

    note = body.get("note")
    client_ip = request.client.host if request.client else None

    try:
        asgn = assign_asset(
            db=db,
            asset_id=asset_id,
            person_id=int(person_id),
            borrowed_at=borrowed_at,
            note=note,
            user_id=user.id,
            ip_address=client_ip,
        )
        db.commit()
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc))

    return JSONResponse(
        content={
            "success": True,
            "message": "Bàn giao thiết bị thành công.",
            "assignment_id": asgn.id,
            "asset_status": "IN_USE",
        }
    )


@router.post("/assets/{asset_id}/return")
async def api_return_asset(
    asset_id: int,
    request: Request,
    db: Session = Depends(get_db),
) -> JSONResponse:
    """Thu hồi thiết bị về kho hoặc đưa đi sửa chữa (Return)."""
    user = get_current_actor(request, db)
    if not (
        has_permission(db, user, Module.ASSETS, PermissionAction.CHANGE)
        or has_permission(db, user, Module.ASSETS, PermissionAction.ADD)
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bạn không có quyền thu hồi thiết bị.",
        )

    try:
        body: dict[str, Any] = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Dữ liệu JSON không hợp lệ.")

    returned_at_raw = body.get("returned_at")
    if returned_at_raw:
        try:
            returned_at = dt.date.fromisoformat(str(returned_at_raw).strip())
        except ValueError:
            raise HTTPException(status_code=400, detail="Định dạng ngày thu hồi không hợp lệ (YYYY-MM-DD).")
    else:
        returned_at = dt.date.today()

    return_status_raw = body.get("return_status", "IN_STOCK")
    try:
        return_status = AssetStatus(str(return_status_raw).strip())
    except ValueError:
        return_status = AssetStatus.IN_STOCK

    note = body.get("note")
    client_ip = request.client.host if request.client else None

    try:
        asgn = return_asset(
            db=db,
            asset_id=asset_id,
            returned_at=returned_at,
            return_status=return_status,
            note=note,
            user_id=user.id,
            ip_address=client_ip,
        )
        db.commit()
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc))

    return JSONResponse(
        content={
            "success": True,
            "message": "Thu hồi thiết bị thành công.",
            "assignment_id": asgn.id,
            "asset_status": return_status.value,
        }
    )


@router.get("/assets/{asset_id}/history")
def api_get_asset_history(
    asset_id: int,
    request: Request,
    db: Session = Depends(get_db),
) -> JSONResponse:
    """Lấy danh sách lịch sử bàn giao của một thiết bị."""
    user = get_current_actor(request, db)
    if not has_permission(db, user, Module.ASSETS, PermissionAction.VIEW):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bạn không có quyền xem thông tin tài sản.",
        )

    history = get_asset_assignment_history(db, asset_id)
    return JSONResponse(
        content=[
            {
                "id": a.id,
                "person_name": a.person.full_name if a.person else "Chưa rõ",
                "staff_code": a.person.staff_code if a.person else "",
                "department": a.person.department.name_en if a.person and a.person.department else "",
                "borrowed_at": a.borrowed_at.strftime("%d/%m/%Y") if a.borrowed_at else "",
                "returned_at": a.returned_at.strftime("%d/%m/%Y") if a.returned_at else None,
                "note": a.note or "",
                "is_active": a.returned_at is None,
            }
            for a in history
        ]
    )
