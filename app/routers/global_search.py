"""Router cho tính năng Tìm kiếm toàn cục (Global Search - FR-04).

Hỗ trợ tìm kiếm nhanh theo:
- Asset: mã GA, mã vendor, model, serial, HWID, MAC LAN, MAC Wi-Fi
- Person: họ tên, mã nhân viên (staff code), user ID, email
- Contract: mã hợp đồng, tên vendor
- AccessCard: số thẻ
- Phone: số extension, tên thiết bị thoại
- License: tên phần mềm (name_en, name_ja), ghi chú

Tuân thủ nghiêm ngặt RBAC: chỉ trả về kết quả ở các module mà người dùng có quyền VIEW.
"""

from __future__ import annotations

from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.admin import get_admin
from app.core.i18n import get_current_lang, translate
from app.core.permissions import has_permission
from app.core.security import verify_session_token
from app.db import get_db
from app.enums import Module, PermissionAction
from app.models import (
    AccessCard,
    Asset,
    Contract,
    License,
    LicenseProduct,
    Person,
    Phone,
    User,
)

router = APIRouter(prefix="/admin", tags=["Global Search"])


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


@router.get("/global-search", response_class=HTMLResponse)
async def global_search_view(
    request: Request,
    q: str = "",
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Trang kết quả tìm kiếm toàn cục đa phân hệ (FR-04)."""
    user = get_current_actor(request, db)
    current_lang = get_current_lang(request)
    admin = get_admin()

    clean_query = q.strip()
    pattern = f"%{clean_query}%"

    results: dict[str, list[Any]] = {
        "assets": [],
        "persons": [],
        "contracts": [],
        "cards": [],
        "phones": [],
        "licenses": [],
    }
    total_count = 0

    if clean_query:
        # 1. Assets (Mã GA, Vendor code, Model, Serial, HWID, MAC LAN/Wi-Fi)
        if has_permission(db, user, Module.ASSETS, PermissionAction.VIEW):
            assets = db.scalars(
                select(Asset)
                .options(selectinload(Asset.category))
                .where(
                    Asset.is_deleted.is_(False),
                    or_(
                        Asset.asset_code.ilike(pattern),
                        Asset.vendor_code.ilike(pattern),
                        Asset.serial.ilike(pattern),
                        Asset.hwid.ilike(pattern),
                        Asset.mac_ethernet.ilike(pattern),
                        Asset.mac_wifi.ilike(pattern),
                        Asset.model.ilike(pattern),
                    ),
                )
                .order_by(Asset.asset_code.asc())
                .limit(25)
            ).all()
            results["assets"] = assets
            total_count += len(assets)

        # 2. Persons (Họ tên, Staff code, User ID, Email)
        if has_permission(db, user, Module.PERSONS, PermissionAction.VIEW):
            persons = db.scalars(
                select(Person)
                .options(selectinload(Person.department))
                .where(
                    Person.is_deleted.is_(False),
                    or_(
                        Person.full_name.ilike(pattern),
                        Person.staff_code.ilike(pattern),
                        Person.user_login_id.ilike(pattern),
                        Person.email.ilike(pattern),
                    ),
                )
                .order_by(Person.staff_code.asc())
                .limit(25)
            ).all()
            results["persons"] = persons
            total_count += len(persons)

        # 3. Contracts (Mã hợp đồng, Tên nhà cung cấp)
        if has_permission(db, user, Module.CONTRACTS, PermissionAction.VIEW):
            contracts = db.scalars(
                select(Contract)
                .where(
                    Contract.is_deleted.is_(False),
                    or_(
                        Contract.code.ilike(pattern),
                        Contract.vendor_name.ilike(pattern),
                    ),
                )
                .order_by(Contract.code.asc())
                .limit(25)
            ).all()
            results["contracts"] = contracts
            total_count += len(contracts)

        # 4. Access Cards (Số thẻ)
        if has_permission(db, user, Module.CARDS, PermissionAction.VIEW):
            cards = db.scalars(
                select(AccessCard)
                .where(
                    AccessCard.is_deleted.is_(False),
                    AccessCard.card_no.ilike(pattern),
                )
                .order_by(AccessCard.card_no.asc())
                .limit(25)
            ).all()
            results["cards"] = cards
            total_count += len(cards)

        # 5. Phones (Số máy nhánh extension, Tên thiết bị)
        if has_permission(db, user, Module.PHONES, PermissionAction.VIEW):
            phones = db.scalars(
                select(Phone)
                .options(selectinload(Phone.location))
                .where(
                    Phone.is_deleted.is_(False),
                    or_(
                        Phone.extension_number.ilike(pattern),
                        Phone.device_name.ilike(pattern),
                    ),
                )
                .order_by(Phone.extension_number.asc())
                .limit(25)
            ).all()
            results["phones"] = phones
            total_count += len(phones)

        # 6. Licenses (Tên phần mềm, Ghi chú)
        if has_permission(db, user, Module.LICENSES, PermissionAction.VIEW):
            licenses = db.scalars(
                select(License)
                .join(License.product)
                .options(selectinload(License.product))
                .where(
                    License.is_deleted.is_(False),
                    or_(
                        LicenseProduct.name.ilike(pattern),
                        License.note.ilike(pattern),
                    ),
                )
                .order_by(License.id.asc())
                .limit(25)
            ).all()
            results["licenses"] = licenses
            total_count += len(licenses)

    context = {
        "request": request,
        "admin": admin,
        "current_lang": current_lang,
        "query": clean_query,
        "results": results,
        "total_count": total_count,
        "title": translate("Tìm kiếm toàn cục", current_lang),
        "subtitle": f"{total_count} " + translate("kết quả tìm kiếm cho", current_lang) + f' "{clean_query}"',
    }

    return await admin.templates.TemplateResponse(request, "sqladmin/global_search.html", context)
