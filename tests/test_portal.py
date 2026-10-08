"""Kiểm thử cho luồng điều hướng chuyển tiếp Portal sang Cổng Quản trị Thống nhất SQLAdmin."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db import get_db
from app.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def override_db(db: Session, monkeypatch):
    """Đảm bảo TestClient dùng chung transaction với fixture db trong test."""
    class _MockSessionMaker:
        class_ = Session

        def __call__(self, *args, **kwargs):
            return self

        def __enter__(self):
            return db

        def __exit__(self, exc_type, exc_val, exc_tb):
            pass

    mock_maker = _MockSessionMaker()
    app.dependency_overrides[get_db] = lambda: db
    monkeypatch.setattr("app.admin.SessionLocal", mock_maker)

    yield
    app.dependency_overrides.clear()


def test_portal_home_redirects_to_admin(client: TestClient):
    """Truy cập trang chủ / phải chuyển hướng trực tiếp sang /admin."""
    res = client.get("/", follow_redirects=False)
    assert res.status_code in (302, 303)
    assert res.headers["location"] == "/admin"


def test_portal_login_get_redirects_to_admin_login(client: TestClient):
    """GET /login phải chuyển hướng sang trang đăng nhập quản trị /admin/login."""
    res = client.get("/login", follow_redirects=False)
    assert res.status_code in (302, 303)
    assert res.headers["location"] == "/admin/login"


def test_portal_login_post_redirects_to_admin_login(client: TestClient):
    """POST /login phải chuyển hướng sang trang đăng nhập quản trị /admin/login."""
    res = client.post("/login", data={"username": "any", "password": "any"}, follow_redirects=False)
    assert res.status_code in (302, 303)
    assert res.headers["location"] == "/admin/login"


def test_portal_logout_redirects_to_admin_logout(client: TestClient):
    """GET /logout phải xoá cookie và chuyển hướng sang /admin/logout."""
    res = client.get("/logout", follow_redirects=False)
    assert res.status_code in (302, 303)
    assert res.headers["location"] == "/admin/logout"


def test_portal_assets_redirects_to_admin_asset_list(client: TestClient):
    """GET /assets phải chuyển hướng sang danh sách tài sản /admin/asset/list."""
    res = client.get("/assets", follow_redirects=False)
    assert res.status_code in (302, 303)
    assert res.headers["location"] == "/admin/asset/list"


def test_portal_assignments_redirects_to_admin_assignment_list(client: TestClient):
    """GET /assignments phải chuyển hướng sang cấp phát /admin/assignment/list."""
    res = client.get("/assignments", follow_redirects=False)
    assert res.status_code in (302, 303)
    assert res.headers["location"] == "/admin/assignment/list"


def test_portal_cards_redirects_to_admin_card_list(client: TestClient):
    """GET /cards phải chuyển hướng sang danh sách thẻ /admin/access-card/list."""
    res = client.get("/cards", follow_redirects=False)
    assert res.status_code in (302, 303)
    assert res.headers["location"] == "/admin/access-card/list"


def test_portal_phones_redirects_to_admin_phone_list(client: TestClient):
    """GET /phones phải chuyển hướng sang danh bạ /admin/phone/list."""
    res = client.get("/phones", follow_redirects=False)
    assert res.status_code in (302, 303)
    assert res.headers["location"] == "/admin/phone/list"


def test_admin_login_page_renders_cleanly(client: TestClient):
    """Trang /admin/login phải hiển thị đầy đủ tiêu đề Tokuyama, form đăng nhập và nhãn."""
    res = client.get("/admin/login")
    assert res.status_code == 200
    html = res.text
    assert "Hệ thống Quản lý Tài sản CNTT Tokuyama Vietnam" in html
    assert 'name="username"' in html
    assert 'name="password"' in html
