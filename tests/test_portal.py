"""Kiểm thử cho Cổng Web Portal và luồng đăng nhập người dùng."""

from __future__ import annotations

import re
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password, create_session_token
from app.db import get_db
from app.enums import RoleCode
from app.main import app
from app.models import AuditLog, Role, User


@pytest.fixture
def client():
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


def _ensure_role(db: Session, code: str, name_en: str) -> Role:
    role = db.scalar(select(Role).where(Role.code == code))
    if not role:
        role = Role(code=code, name_en=name_en)
        db.add(role)
        db.commit()
    return role


def test_portal_login_page_renders(client: TestClient):
    """GET /login phải trả về 200, có chứa trường CSRF token và form đăng nhập."""
    response = client.get("/login")
    assert response.status_code == 200
    html = response.text
    assert "TOKUYAMA VIETNAM" in html
    assert 'name="csrf_token"' in html
    assert 'name="username"' in html
    assert 'name="password"' in html


def test_portal_login_csrf_validation_fails_without_token(client: TestClient):
    """POST /login không có CSRF token phải bị từ chối."""
    response = client.post("/login", data={"username": "itadmin", "password": "any"})
    assert response.status_code in (400, 403) or "CSRF" in response.text


def test_portal_login_wrong_credentials(client: TestClient, db: Session):
    """POST /login sai mật khẩu phải hiển thị thông báo lỗi và ghi nhận LOGIN_FAIL."""
    _ensure_role(db, RoleCode.ADMIN.value, "Administrator")
    get_res = client.get("/login")
    assert get_res.status_code == 200

    match = re.search(r'name="csrf_token"\s+value="([^"]+)"', get_res.text)
    assert match is not None
    csrf_token = match.group(1)

    post_res = client.post(
        "/login",
        data={
            "username": "itadmin",
            "password": "wrong_password_12345",
            "csrf_token": csrf_token,
        },
    )
    assert post_res.status_code == 200
    assert "không chính xác" in post_res.text

    # Kiểm tra audit log có ghi nhận LOGIN_FAIL
    last_log = db.scalar(
        select(AuditLog).order_by(AuditLog.id.desc()).limit(1)
    )
    assert last_log is not None
    assert last_log.action.value == "LOGIN_FAIL"


def test_portal_login_admin_redirect(client: TestClient, db: Session):
    """Tài khoản ADMIN đăng nhập thành công phải được chuyển hướng vào /admin."""
    admin_role = _ensure_role(db, RoleCode.ADMIN.value, "Administrator")
    admin_user = db.scalar(select(User).where(User.username == "test_admin"))
    if not admin_user:
        admin_user = User(
            username="test_admin",
            password_hash=hash_password("admin_pass_123"),
            display_name="Test Administrator",
            role_id=admin_role.id,
            is_active=True,
            is_deleted=False,
        )
        db.add(admin_user)
        db.commit()

    get_res = client.get("/login")
    csrf_token = re.search(r'name="csrf_token"\s+value="([^"]+)"', get_res.text).group(1)

    post_res = client.post(
        "/login",
        data={
            "username": "test_admin",
            "password": "admin_pass_123",
            "csrf_token": csrf_token,
        },
        follow_redirects=False,
    )
    assert post_res.status_code in (302, 303)
    assert post_res.headers["location"] == "/admin"
    assert "itam_session" in post_res.cookies


def test_portal_login_executive_redirect(client: TestClient, db: Session):
    """Tài khoản EXECUTIVE đăng nhập thành công phải được chuyển hướng về trang chủ /."""
    exec_role = _ensure_role(db, RoleCode.EXECUTIVE.value, "Executive")
    exec_user = db.scalar(select(User).where(User.username == "test_exec"))
    if not exec_user:
        exec_user = User(
            username="test_exec",
            password_hash=hash_password("exec_pass_123"),
            display_name="Test Executive",
            role_id=exec_role.id,
            is_active=True,
            is_deleted=False,
        )
        db.add(exec_user)
        db.commit()

    get_res = client.get("/login")
    csrf_token = re.search(r'name="csrf_token"\s+value="([^"]+)"', get_res.text).group(1)

    post_res = client.post(
        "/login",
        data={
            "username": "test_exec",
            "password": "exec_pass_123",
            "csrf_token": csrf_token,
        },
        follow_redirects=False,
    )
    assert post_res.status_code in (302, 303)
    assert post_res.headers["location"] == "/"
    assert "itam_session" in post_res.cookies


def test_portal_unauthenticated_dashboard_redirect(client: TestClient):
    """Chưa đăng nhập truy cập / phải bị chuyển hướng về /login."""
    response = client.get("/", follow_redirects=False)
    assert response.status_code in (302, 303)
    assert response.headers["location"] == "/login"


def test_portal_executive_dashboard_access(client: TestClient, db: Session):
    """Tài khoản EXECUTIVE đã đăng nhập truy cập / xem được nội dung Dashboard và KPI."""
    exec_role = _ensure_role(db, RoleCode.EXECUTIVE.value, "Executive")
    exec_user = db.scalar(select(User).where(User.username == "test_exec_view"))
    if not exec_user:
        exec_user = User(
            username="test_exec_view",
            password_hash=hash_password("exec_pass_123"),
            display_name="Test Executive View",
            role_id=exec_role.id,
            is_active=True,
            is_deleted=False,
        )
        db.add(exec_user)
        db.commit()

    token = create_session_token(
        {
            "user_id": exec_user.id,
            "username": exec_user.username,
            "role": exec_user.role.code,
        }
    )

    client.cookies.set("itam_session", token)
    response = client.get("/")
    assert response.status_code == 200
    html = response.text
    assert "Tổng quan Quản trị Tài sản" in html
    assert "Xin chào, Test Executive View" in html
    assert "Tổng số thiết bị" in html


def test_portal_logout(client: TestClient):
    """GET /logout phải xóa phiên và chuyển hướng về /login."""
    response = client.get("/logout", follow_redirects=False)
    assert response.status_code in (302, 303)
    assert response.headers["location"] == "/login"
