"""Màn hình Sổ tổng: xem và sửa laptop, người giữ trên một bảng, thay cho file Excel."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from app.admin import get_admin
from app.core.i18n import get_current_lang
from app.core.inputs import optional_text, read_json_object, require_positive_int
from app.core.permissions import has_permission
from app.db import get_db
from app.enums import Module, PermissionAction
from app.models import User
from app.routers.assets import get_current_actor
from app.services import ledger_service

router = APIRouter(prefix="/admin", tags=["So tong"])


def _forbidden() -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Bạn không có quyền thực hiện thao tác này.")


def _require_ledger_view(request: Request, db: Session) -> User:
    """Mỗi dòng gộp dữ liệu của ba phân hệ nên phải được xem cả ba."""
    user = get_current_actor(request, db)
    for module in (Module.ASSETS, Module.PERSONS, Module.ASSIGNMENTS):
        if not has_permission(db, user, module, PermissionAction.VIEW):
            raise _forbidden()
    return user


def _rows(db: Session, user: User) -> list[dict[str, Any]]:
    return ledger_service.build_ledger_rows(
        db, include_secret_flag=has_permission(db, user, Module.SECRETS, PermissionAction.VIEW)
    )


def _rows_touching(db: Session, user: User, row_id: str, person_id: int | None = None) -> list[dict[str, Any]]:
    """Dòng vừa sửa cộng mọi dòng cùng người: sửa email một người phải đổi ở tất cả máy họ giữ."""
    rows = _rows(db, user)
    edited = next((r for r in rows if r["id"] == row_id), None)
    pid = person_id or (edited["person_id"] if edited else None)
    return [r for r in rows if r["id"] == row_id or (pid and r["person_id"] == pid)]


@router.get("/so-tong", response_class=HTMLResponse, response_model=None)
async def so_tong_page(request: Request, db: Session = Depends(get_db)) -> Response:
    # Đây là trang đích sau đăng nhập: hết phiên thì về màn hình đăng nhập, không hiện JSON thô.
    try:
        user = _require_ledger_view(request, db)
    except HTTPException as exc:
        if exc.status_code == status.HTTP_401_UNAUTHORIZED:
            return RedirectResponse("/admin/login", status_code=302)
        raise
    admin = get_admin()
    if not admin:
        raise HTTPException(status_code=500, detail="Giao diện quản trị chưa sẵn sàng.")
    context = {
        "request": request,
        "admin": admin,
        "current_lang": get_current_lang(request),
        "title": "Sổ tổng",
        "perms": {
            "assets": has_permission(db, user, Module.ASSETS, PermissionAction.CHANGE),
            "persons": has_permission(db, user, Module.PERSONS, PermissionAction.CHANGE),
            "secrets": has_permission(db, user, Module.SECRETS, PermissionAction.VIEW),
        },
        "departments": ledger_service.list_department_names(db),
        "software_tags": ledger_service.list_software_tags(db),
    }
    return await admin.templates.TemplateResponse(request, "sqladmin/so_tong.html", context)


@router.get("/api/so-tong")
def so_tong_rows(request: Request, db: Session = Depends(get_db)) -> JSONResponse:
    user = _require_ledger_view(request, db)
    return JSONResponse(content=_rows(db, user))


@router.patch("/api/so-tong/cell")
async def so_tong_edit_cell(request: Request, db: Session = Depends(get_db)) -> JSONResponse:
    user = _require_ledger_view(request, db)
    body = await read_json_object(request)
    field = body.get("field")
    try:
        row_kind, row_pk = ledger_service.parse_row_id(body.get("id"))
        if not isinstance(field, str):
            raise ValueError("Ô này không sửa trực tiếp được.")
        module = ledger_service.module_of_field(row_kind, field)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if not has_permission(db, user, module, PermissionAction.CHANGE):
        raise _forbidden()

    value = optional_text(body.get("value"), 2000, "Giá trị")
    client_ip = request.client.host if request.client else None
    try:
        ledger_service.update_cell(db, row_kind, row_pk, field, value, user_id=user.id, ip_address=client_ip)
        db.commit()
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc))
    person_id = row_pk if row_kind == "person" else None
    return JSONResponse(content={"success": True, "rows": _rows_touching(db, user, body["id"], person_id)})


@router.put("/api/so-tong/software")
async def so_tong_set_software(request: Request, db: Session = Depends(get_db)) -> JSONResponse:
    user = _require_ledger_view(request, db)
    if not has_permission(db, user, Module.ASSETS, PermissionAction.CHANGE):
        raise _forbidden()
    body = await read_json_object(request)
    asset_id = require_positive_int(body.get("asset_id"), "Thiết bị không hợp lệ.")
    codes = body.get("codes")
    if not isinstance(codes, list) or not all(isinstance(c, str) for c in codes):
        raise HTTPException(status_code=400, detail="Danh sách phần mềm không hợp lệ.")
    client_ip = request.client.host if request.client else None
    try:
        ledger_service.set_asset_software(db, asset_id, codes, user_id=user.id, ip_address=client_ip)
        db.commit()
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc))
    return JSONResponse(content={"success": True, "rows": _rows_touching(db, user, f"asset-{asset_id}")})
