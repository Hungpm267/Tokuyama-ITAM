"""Router nhận Phần mềm cho Hạng mục Hợp đồng loại SOFTWARE.

Song song với "Nhập kho theo lô" của phần cứng (batch_receive.py): thay vì nhập
serial từng máy, người dùng ghi nhận một gói license (sản phẩm, số seat, hạn dùng).
Logic nghiệp vụ nằm ở `license_service.receive_license_for_line`.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.admin import get_admin, invalidate_model_count_cache
from app.core.i18n import get_current_lang
from app.core.inputs import optional_text, read_json_object, require_positive_int
from app.core.permissions import has_permission
from app.db import get_db
from app.enums import ContractItemKind, Module, PermissionAction
from app.models import ContractLine, License, LicenseProduct, User
from app.routers.batch_receive import get_current_actor
from app.services.license_service import receive_license_for_line

router = APIRouter(prefix="/admin/contract-line", tags=["Software Receive"])


def check_software_receive_permission(db: Session, user: User) -> None:
    """Nhận phần mềm tạo ra một gói license -> cần quyền ADD trên module LICENSES."""
    if not has_permission(db, user, Module.LICENSES, PermissionAction.ADD):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bạn không có quyền thực hiện thao tác này.",
        )


def _parse_date(raw: Any, label: str) -> dt.date | None:
    if raw is None or str(raw).strip() == "":
        return None
    try:
        return dt.date.fromisoformat(str(raw).strip())
    except ValueError:
        raise HTTPException(status_code=400, detail=f"{label} không hợp lệ (định dạng YYYY-MM-DD).")


@router.get("/{line_id}/receive-software", response_class=HTMLResponse)
async def software_receive_page(
    line_id: int,
    request: Request,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Màn hình nhận phần mềm cho một hạng mục hợp đồng."""
    user = get_current_actor(request, db)
    check_software_receive_permission(db, user)

    line = db.scalar(
        select(ContractLine)
        .options(
            selectinload(ContractLine.contract),
            selectinload(ContractLine.licenses).selectinload(License.product),
        )
        .where(ContractLine.id == line_id, ContractLine.is_deleted.is_(False))
    )
    if not line or not line.contract or line.contract.is_deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Hạng mục hợp đồng không tồn tại hoặc đã bị xóa.",
        )
    # Hạng mục phần cứng nhận bằng serial từng máy: chuyển về màn hình Nhập kho theo lô.
    if line.item_kind != ContractItemKind.SOFTWARE:
        return RedirectResponse(f"/admin/contract-line/{line.id}/receive", status_code=303)

    products = db.scalars(
        select(LicenseProduct)
        .where(LicenseProduct.is_deleted.is_(False))
        .order_by(LicenseProduct.name)
    ).all()

    # Gợi ý sản phẩm có tên xuất hiện trong tên hạng mục (vd. "Office LTSC 2024 x30")
    item_type_lower = (line.item_type or "").lower()
    suggested_product_id = next(
        (p.id for p in products if p.name and p.name.lower() in item_type_lower), None
    )

    admin = get_admin()
    if not admin:
        raise HTTPException(status_code=500, detail="Giao diện quản trị chưa sẵn sàng.")

    context = {
        "request": request,
        "admin": admin,
        "contract_line": line,
        "contract": line.contract,
        "products": products,
        "suggested_product_id": suggested_product_id,
        "received_licenses": [lic for lic in line.licenses if not lic.is_deleted],
        "current_lang": get_current_lang(request),
    }
    return await admin.templates.TemplateResponse(request, "sqladmin/software_receive.html", context)


@router.post("/{line_id}/receive-software")
async def process_software_receive(
    line_id: int,
    request: Request,
    db: Session = Depends(get_db),
) -> JSONResponse:
    """Ghi nhận một gói phần mềm đã nhận cho hạng mục hợp đồng."""
    user = get_current_actor(request, db)
    check_software_receive_permission(db, user)

    body = await read_json_object(request)

    product_id = require_positive_int(body.get("product_id"), "Vui lòng chọn sản phẩm phần mềm.")
    seats = require_positive_int(body.get("seats"), "Số lượng bản quyền phải là số nguyên lớn hơn 0.")
    start_date = _parse_date(body.get("start_date"), "Ngày kích hoạt")
    expiry_date = _parse_date(body.get("expiry_date"), "Ngày hết hạn")
    note = optional_text(body.get("note"), 2000, "Ghi chú")
    client_ip = request.client.host if request.client else None

    try:
        lic = receive_license_for_line(
            db=db,
            line_id=line_id,
            product_id=product_id,
            seats=seats,
            start_date=start_date,
            expiry_date=expiry_date,
            note=note,
            user_id=user.id,
            ip_address=client_ip,
        )
        db.commit()
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc))

    invalidate_model_count_cache(License)

    return JSONResponse(
        content={
            "success": True,
            "license_id": lic.id,
            "message": f"Đã ghi nhận {seats} bản quyền cho hạng mục này.",
            "redirect_url": f"/admin/contract-line/details/{line_id}",
        }
    )
