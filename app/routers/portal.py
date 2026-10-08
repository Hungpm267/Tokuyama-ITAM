"""Router cho Cổng Web Portal và luồng đăng nhập người dùng."""

from __future__ import annotations

import datetime as dt
import hmac
from pathlib import Path
import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.audit import audit_login
from app.core.security import (
    create_session_token,
    verify_password,
    verify_session_token,
)
from app.db import get_db
from app.enums import AssetStatus, RoleCode
from app.models import (
    AccessCard,
    Asset,
    Assignment,
    CardLoan,
    License,
    LicenseProduct,
    Person,
    User,
)
from app.services.phone_service import list_phones

BASE_DIR = Path(__file__).resolve().parent.parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

router = APIRouter(tags=["Web Portal"])


def get_authenticated_user(request: Request, db: Session) -> User | None:
    """Trích xuất người dùng hiện tại từ session hoặc cookie itam_session."""
    user_id = request.session.get("user_id") if hasattr(request, "session") else None

    if not user_id:
        token = request.cookies.get("itam_session")
        if token:
            payload = verify_session_token(token)
            if payload and "user_id" in payload:
                user_id = payload["user_id"]

    if not user_id:
        return None

    return db.scalar(
        select(User).where(
            User.id == user_id,
            User.is_active.is_(True),
            User.is_deleted.is_(False),
        )
    )


@router.get("/login", response_class=HTMLResponse)
def login_page(
    request: Request,
    db: Session = Depends(get_db),
):
    """Hiển thị màn hình đăng nhập công khai hoặc chuyển hướng nếu đã đăng nhập."""
    current_user = get_authenticated_user(request, db)
    if current_user:
        if current_user.role and current_user.role.code == RoleCode.ADMIN.value:
            return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)

    # Sinh CSRF token ngẫu nhiên lưu vào session
    csrf_token = secrets.token_hex(16)
    if hasattr(request, "session"):
        request.session["csrf_token"] = csrf_token

    lang = request.cookies.get("itam_lang", "vi")

    return templates.TemplateResponse(
        request=request,
        name="portal/login.html",
        context={
            "csrf_token": csrf_token,
            "current_lang": lang,
            "error": None,
            "username": "",
        },
    )


@router.post("/login", response_class=HTMLResponse)
def handle_login(
    request: Request,
    response: Response,
    username: Annotated[str, Form()] = "",
    password: Annotated[str, Form()] = "",
    csrf_token: Annotated[str, Form()] = "",
    db: Session = Depends(get_db),
):
    """Xử lý đăng nhập form HTML, bảo vệ CSRF, xác thực Argon2id và điều hướng theo vai trò."""
    client_ip = request.client.host if request.client else None
    username_clean = username.strip()
    lang = request.cookies.get("itam_lang", "vi")

    # 1. Kiểm tra CSRF token
    session_csrf = request.session.get("csrf_token") if hasattr(request, "session") else None
    if not session_csrf or not csrf_token or not hmac.compare_digest(session_csrf, csrf_token):
        return templates.TemplateResponse(
            request=request,
            name="portal/login.html",
            context={
                "csrf_token": session_csrf or secrets.token_hex(16),
                "current_lang": lang,
                "error": "Yêu cầu không hợp lệ hoặc phiên bảo mật (CSRF) đã hết hạn. Vui lòng thử lại.",
                "username": username_clean,
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    # 2. Tìm kiếm User
    user = db.scalar(
        select(User).where(
            User.username == username_clean,
            User.is_active.is_(True),
            User.is_deleted.is_(False),
        )
    )

    # 3. Kiểm tra mật khẩu Argon2id
    if not user or not verify_password(password, user.password_hash):
        audit_login(db, user_id=user.id if user else None, success=False, username=username_clean, ip_address=client_ip)
        db.commit()
        return templates.TemplateResponse(
            request=request,
            name="portal/login.html",
            context={
                "csrf_token": session_csrf,
                "current_lang": lang,
                "error": "Tên đăng nhập hoặc mật khẩu không chính xác.",
                "username": username_clean,
            },
            status_code=status.HTTP_200_OK,
        )

    # 4. Đăng nhập thành công
    user.last_login_at = dt.datetime.now(dt.timezone.utc)
    audit_login(db, user_id=user.id, success=True, username=username_clean, ip_address=client_ip)
    db.commit()

    # Tạo JWT session token
    token = create_session_token({
        "user_id": user.id,
        "username": user.username,
        "role": user.role.code,
    })

    if hasattr(request, "session"):
        request.session["user_id"] = user.id

    # 5. Phân luồng điều hướng theo vai trò (Role-based redirect)
    redirect_target = "/admin" if (user.role and user.role.code == RoleCode.ADMIN.value) else "/"
    redirect_res = RedirectResponse(url=redirect_target, status_code=status.HTTP_303_SEE_OTHER)

    redirect_res.set_cookie(
        key="itam_session",
        value=token,
        httponly=True,
        samesite="lax",
        max_age=1800,  # 30 phút
    )
    return redirect_res


@router.get("/", response_class=HTMLResponse)
def portal_home(
    request: Request,
    db: Session = Depends(get_db),
):
    """Trang chủ Cổng Web Portal (Dashboard cho Executive và GA Manager)."""
    current_user = get_authenticated_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    # Nếu là ADMIN: tự động chuyển tiếp sang /admin (theo rule đã chốt)
    # Tuy nhiên nếu query param ?portal=1 thì cho phép xem portal
    if current_user.role and current_user.role.code == RoleCode.ADMIN.value and request.query_params.get("portal") != "1":
        return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)

    # Truy vấn dữ liệu KPI (FR-17)
    today = dt.date.today()
    sixty_days_later = today + dt.timedelta(days=60)

    total_assets = db.scalar(select(func.count(Asset.id)).where(Asset.is_deleted.is_(False))) or 0
    in_stock_assets = db.scalar(
        select(func.count(Asset.id)).where(
            Asset.is_deleted.is_(False),
            Asset.status == AssetStatus.IN_STOCK,
        )
    ) or 0
    in_use_assets = db.scalar(
        select(func.count(Asset.id)).where(
            Asset.is_deleted.is_(False),
            Asset.status == AssetStatus.IN_USE,
        )
    ) or 0
    repair_assets = db.scalar(
        select(func.count(Asset.id)).where(
            Asset.is_deleted.is_(False),
            Asset.status == AssetStatus.REPAIR,
        )
    ) or 0

    stats = {
        "total_assets": total_assets,
        "in_stock_assets": in_stock_assets,
        "in_use_assets": in_use_assets,
        "repair_assets": repair_assets,
    }

    # License sắp hết hạn (trong vòng 60 ngày)
    expiring_rows = db.execute(
        select(License, LicenseProduct.name)
        .join(LicenseProduct, License.product_id == LicenseProduct.id)
        .where(
            License.is_deleted.is_(False),
            License.expiry_date.is_not(None),
            License.expiry_date >= today,
            License.expiry_date <= sixty_days_later,
        )
        .order_by(License.expiry_date.asc())
        .limit(10)
    ).all()

    expiring_licenses = [
        {
            "product_name": row[1],
            "seats": row[0].seats,
            "expiry_date": row[0].expiry_date.strftime("%d/%m/%Y") if row[0].expiry_date else "",
        }
        for row in expiring_rows
    ]

    # Thẻ ra vào đang cho mượn
    loan_rows = db.execute(
        select(CardLoan, AccessCard.card_no, Person.full_name)
        .join(AccessCard, CardLoan.card_id == AccessCard.id)
        .outerjoin(Person, CardLoan.person_id == Person.id)
        .where(CardLoan.returned_at.is_(None))
        .order_by(CardLoan.borrowed_at.desc())
        .limit(10)
    ).all()

    active_card_loans = [
        {
            "card_no": row[1],
            "borrower_name": row[2] or row[0].external_name or "Chưa rõ",
            "borrowed_at": row[0].borrowed_at.strftime("%d/%m/%Y") if row[0].borrowed_at else "",
            "is_overdue": bool(row[0].expected_return_at and row[0].expected_return_at < today),
        }
        for row in loan_rows
    ]

    lang = request.cookies.get("itam_lang", "vi")

    return templates.TemplateResponse(
        request=request,
        name="portal/dashboard.html",
        context={
            "user": current_user,
            "current_lang": lang,
            "active_page": "dashboard",
            "stats": stats,
            "expiring_licenses": expiring_licenses,
            "active_card_loans": active_card_loans,
        },
    )


@router.get("/assets", response_class=HTMLResponse)
def portal_assets(
    request: Request,
    q: str | None = None,
    status_filter: str | None = None,
    db: Session = Depends(get_db),
):
    """Tra cứu danh sách Thiết bị / Tài sản IT (dành cho Ban Giám đốc và Tổng vụ)."""
    current_user = get_authenticated_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    query = (
        select(Asset)
        .options(
            selectinload(Asset.category),
            selectinload(Asset.assignments).selectinload(Assignment.person).selectinload(Person.department),
        )
        .where(Asset.is_deleted.is_(False))
    )

    if q and q.strip():
        term = f"%{q.strip()}%"
        query = query.where(
            or_(
                Asset.asset_code.ilike(term),
                Asset.vendor_code.ilike(term),
                Asset.model.ilike(term),
                Asset.serial_number.ilike(term),
            )
        )

    if status_filter and status_filter.strip():
        query = query.where(Asset.status == status_filter.strip())

    assets = list(db.scalars(query.order_by(Asset.id.desc()).limit(150)).all())
    lang = request.cookies.get("itam_lang", "vi")

    return templates.TemplateResponse(
        request=request,
        name="portal/assets.html",
        context={
            "user": current_user,
            "current_lang": lang,
            "active_page": "assets",
            "assets": assets,
            "q": q or "",
            "status_filter": status_filter or "",
            "AssetStatus": AssetStatus,
        },
    )


@router.get("/assignments", response_class=HTMLResponse)
def portal_assignments(
    request: Request,
    q: str | None = None,
    active_only: bool = False,
    db: Session = Depends(get_db),
):
    """Lịch sử và trạng thái Cấp phát / Mượn - Trả thiết bị IT."""
    current_user = get_authenticated_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    query = (
        select(Assignment)
        .options(
            selectinload(Assignment.asset).selectinload(Asset.category),
            selectinload(Assignment.person).selectinload(Person.department),
        )
    )

    if active_only:
        query = query.where(Assignment.returned_at.is_(None))

    if q and q.strip():
        term = f"%{q.strip()}%"
        query = query.join(Assignment.person).where(
            or_(
                Person.full_name.ilike(term),
                Person.staff_code.ilike(term),
            )
        )

    assignments = list(db.scalars(query.order_by(Assignment.borrowed_at.desc()).limit(150)).all())
    lang = request.cookies.get("itam_lang", "vi")

    return templates.TemplateResponse(
        request=request,
        name="portal/assignments.html",
        context={
            "user": current_user,
            "current_lang": lang,
            "active_page": "assignments",
            "assignments": assignments,
            "q": q or "",
            "active_only": active_only,
        },
    )


@router.get("/cards", response_class=HTMLResponse)
def portal_cards(
    request: Request,
    q: str | None = None,
    db: Session = Depends(get_db),
):
    """Danh sách Thẻ ra vào và Nhật ký Mượn thẻ."""
    current_user = get_authenticated_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    query = (
        select(AccessCard)
        .options(
            selectinload(AccessCard.loans).selectinload(CardLoan.person),
        )
        .where(AccessCard.is_deleted.is_(False))
    )

    if q and q.strip():
        term = f"%{q.strip()}%"
        query = query.where(AccessCard.card_no.ilike(term))

    cards = list(db.scalars(query.order_by(AccessCard.id.asc()).limit(150)).all())
    today = dt.date.today()
    lang = request.cookies.get("itam_lang", "vi")

    return templates.TemplateResponse(
        request=request,
        name="portal/cards.html",
        context={
            "user": current_user,
            "current_lang": lang,
            "active_page": "cards",
            "cards": cards,
            "today": today,
            "q": q or "",
        },
    )


@router.get("/phones", response_class=HTMLResponse)
def portal_phones(
    request: Request,
    q: str | None = None,
    db: Session = Depends(get_db),
):
    """Danh bạ máy nhánh và vị trí phòng ban (Phone List - FR-15)."""
    current_user = get_authenticated_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    phones = list_phones(db, active_only=False, search=q)
    lang = request.cookies.get("itam_lang", "vi")

    return templates.TemplateResponse(
        request=request,
        name="portal/phones.html",
        context={
            "user": current_user,
            "current_lang": lang,
            "active_page": "phones",
            "phones": phones,
            "q": q or "",
        },
    )


@router.get("/logout")
def logout(
    request: Request,
):
    """Đăng xuất, xoá session và chuyển hướng về /login."""
    if hasattr(request, "session"):
        request.session.clear()

    res = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    res.delete_cookie("itam_session")
    return res
