"""Router chuyển hướng các đường dẫn Portal sang Cổng Quản trị Thống nhất SQLAdmin."""

from __future__ import annotations

from fastapi import APIRouter, Request, status
from fastapi.responses import RedirectResponse

router = APIRouter(tags=["Web Portal"])


@router.get("/")
def portal_home() -> RedirectResponse:
    """Chuyển hướng toàn bộ truy cập trang chủ sang Cổng Quản trị /admin."""
    return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/login")
@router.post("/login")
def login_redirect() -> RedirectResponse:
    """Chuyển hướng toàn bộ luồng đăng nhập sang Cổng Đăng nhập Quản trị /admin/login."""
    return RedirectResponse(url="/admin/login", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/logout")
def logout(request: Request) -> RedirectResponse:
    """Đăng xuất phiên làm việc và chuyển hướng sang /admin/logout."""
    if hasattr(request, "session"):
        request.session.clear()
    res = RedirectResponse(url="/admin/logout", status_code=status.HTTP_303_SEE_OTHER)
    res.delete_cookie("itam_session")
    res.delete_cookie("admin_session")
    return res


@router.get("/assets")
def portal_assets_redirect() -> RedirectResponse:
    """Chuyển hướng danh sách tài sản sang giao diện Quản trị /admin/asset/list."""
    return RedirectResponse(url="/admin/asset/list", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/assignments")
def portal_assignments_redirect() -> RedirectResponse:
    """Chuyển hướng cấp phát sang giao diện Quản trị /admin/assignment/list."""
    return RedirectResponse(url="/admin/assignment/list", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/cards")
def portal_cards_redirect() -> RedirectResponse:
    """Chuyển hướng danh sách thẻ sang giao diện Quản trị /admin/access-card/list."""
    return RedirectResponse(url="/admin/access-card/list", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/phones")
def portal_phones_redirect() -> RedirectResponse:
    """Chuyển hướng danh bạ sang giao diện Quản trị /admin/phone/list."""
    return RedirectResponse(url="/admin/phone/list", status_code=status.HTTP_303_SEE_OTHER)
