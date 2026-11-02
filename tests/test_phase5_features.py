"""Kiểm thử tầng nghiệp vụ và endpoint Phase 5 (FR-15 Danh bạ thoại, FR-18 Xuất CSV)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db import get_db
from app.enums import Module, PermissionAction
from app.main import app
from app.models import RolePermission


# =============================================================================
# 1. Phone Service Tests (FR-15)
# =============================================================================









# =============================================================================
# 2. CSV Export Endpoint Tests (FR-18)
# =============================================================================

@pytest.fixture
def auth_client(db: Session, seed, monkeypatch):
    """Client có cookie phiên xác thực với đầy đủ quyền VIEW."""
    user = seed["user"]
    role = seed["role"]

    # Đảm bảo role có đủ quyền VIEW các module
    modules = [
        Module.ASSETS,
        Module.LICENSES,
        Module.CARDS,
        Module.PERSONS,
        Module.PHONES,
        Module.CONTRACTS,
    ]
    for mod in modules:
        existing = db.query(RolePermission).filter_by(
            role_id=role.id, module=mod.value, action=PermissionAction.VIEW.value
        ).first()
        if not existing:
            db.add(
                RolePermission(
                    role_id=role.id,
                    module=mod.value,
                    action=PermissionAction.VIEW.value,
                )
            )
    db.flush()

    app.dependency_overrides[get_db] = lambda: db

    # Monkeypatch SessionLocal in app.core.permissions
    import app.core.permissions as p_mod
    monkeypatch.setattr(p_mod, "SessionLocal", lambda: db, raising=False)

    from app.core.security import create_session_token
    token = create_session_token({"user_id": user.id, "username": user.username})

    client = TestClient(app)
    client.cookies.set("itam_session", token)

    yield client

    app.dependency_overrides.clear()














# =============================================================================
# 3. Trilingual i18n Tests (VI / EN / JA)
# =============================================================================

def test_i18n_translation_trilingual():
    from app.core.i18n import SUPPORTED_LANGUAGES, translate

    assert "ja" in SUPPORTED_LANGUAGES
    assert "en" in SUPPORTED_LANGUAGES
    assert "vi" in SUPPORTED_LANGUAGES

    # Test translations for all 3 languages
    assert translate("Tổng quan Quản trị", "vi") == "Tổng quan Quản trị"
    assert translate("Tổng quan Quản trị", "en") == "Dashboard"
    assert translate("Tổng quan Quản trị", "ja") == "ダッシュボード"

    assert translate("Đăng xuất", "vi") == "Đăng xuất"
    assert translate("Đăng xuất", "en") == "Sign Out"
    assert translate("Đăng xuất", "ja") == "ログアウト"

    assert translate("Nhân sự", "ja") == "社員・人事"
    assert translate("Tài sản", "ja") == "IT資産・機器"
    assert translate("Thẻ ra vào", "ja") == "入退室カード"


def test_set_language_endpoint_trilingual():
    client = TestClient(app)

    # Chuyển sang tiếng Nhật
    res_ja = client.get("/admin/set-lang?lang=ja&next=/admin", follow_redirects=False)
    assert res_ja.status_code == 303
    assert "itam_lang=ja" in res_ja.headers.get("set-cookie", "")

    # Chuyển sang tiếng Anh
    res_en = client.get("/admin/set-lang?lang=en&next=/admin", follow_redirects=False)
    assert res_en.status_code == 303
    assert "itam_lang=en" in res_en.headers.get("set-cookie", "")

    # Chuyển sang tiếng Việt
    res_vi = client.get("/admin/set-lang?lang=vi&next=/admin", follow_redirects=False)
    assert res_vi.status_code == 303
    assert "itam_lang=vi" in res_vi.headers.get("set-cookie", "")


def test_favicon_endpoints():
    """Kiểm tra favicon hệ thống trả về đúng mã HTTP 200 và nhúng trong HTML."""
    client = TestClient(app)

    # 1. Trình duyệt tự động request /favicon.ico
    res_ico = client.get("/favicon.ico")
    assert res_ico.status_code == 200
    assert "image/png" in res_ico.headers.get("content-type", "")
    assert len(res_ico.content) > 0

    # 2. Static file GET /static/img/tokuyama-favicon.png
    res_static = client.get("/static/img/tokuyama-favicon.png")
    assert res_static.status_code == 200
    assert len(res_static.content) == len(res_ico.content)

    # 3. Template HTML nhúng đúng đường dẫn favicon
    res_login = client.get("/admin/login")
    assert res_login.status_code == 200
    assert "/static/img/tokuyama-favicon.png" in res_login.text


