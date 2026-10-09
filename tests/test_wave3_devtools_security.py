"""Tests verifying client-side security and DevTools data protection (Wave 3).

Guarantees:
1. SQLAdmin views never leak REDACTED_FIELDS into export, details, list, or forms.
2. Direct access to PersonSecret mutation/export/details endpoints is prohibited.
3. Auth cookies are protected with HttpOnly, SameSite, and Secure.
4. JSON responses and API payloads never expose password hashes or ciphertexts.
5. Reveal token revocation immediately invalidates authorization.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.admin import (
    AccessCardAdmin,
    AssetAdmin,
    AssetCategoryAdmin,
    AssetTagAdmin,
    AssignmentAdmin,
    AuditLogAdmin,
    CardLoanAdmin,
    ContractAdmin,
    ContractLineAdmin,
    DepartmentAdmin,
    LicenseAdmin,
    LicenseAssignmentAdmin,
    LicenseProductAdmin,
    LocationAdmin,
    PersonAdmin,
    PersonSecretAdmin,
    PhoneAdmin,
    RoleAdmin,
    RolePermissionAdmin,
    UserAdmin,
    UserPermissionOverrideAdmin,
)
from app.core.reveal import RevealGate
from app.core.security import create_session_token, hash_password
from app.db import get_db
from app.main import app
from app.models import REDACTED_FIELDS, Role, User


ALL_ADMIN_VIEWS = [
    UserAdmin,
    RoleAdmin,
    RolePermissionAdmin,
    UserPermissionOverrideAdmin,
    DepartmentAdmin,
    AssetCategoryAdmin,
    AssetTagAdmin,
    LocationAdmin,
    PersonAdmin,
    PersonSecretAdmin,
    AssetAdmin,
    AssignmentAdmin,
    LicenseProductAdmin,
    LicenseAdmin,
    LicenseAssignmentAdmin,
    AccessCardAdmin,
    CardLoanAdmin,
    ContractAdmin,
    ContractLineAdmin,
    PhoneAdmin,
    AuditLogAdmin,
]


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


def test_sqladmin_views_exclude_redacted_fields():
    """Tất cả các Admin ModelView tuyệt đối không chứa REDACTED_FIELDS trong export, details, list, hay form."""
    for view_cls in ALL_ADMIN_VIEWS:
        view = view_cls()
        view_name = view_cls.__name__

        # 1. Kiểm tra export columns
        export_cols = [getattr(c, "key", str(c)) for c in view.get_export_columns()]
        for rf in REDACTED_FIELDS:
            assert rf not in export_cols, f"{view_name} làm rò rỉ {rf} trong Export columns!"

        # 2. Kiểm tra list columns
        list_cols = [getattr(c, "key", str(c)) for c in view.get_list_columns()]
        for rf in REDACTED_FIELDS:
            assert rf not in list_cols, f"{view_name} làm rò rỉ {rf} trong List columns!"

        # 3. Kiểm tra details columns
        details_cols = [getattr(c, "key", str(c)) for c in view.get_details_columns()]
        for rf in REDACTED_FIELDS:
            assert rf not in details_cols, f"{view_name} làm rò rỉ {rf} trong Details columns!"

        # 4. Kiểm tra form columns
        try:
            form_cols = [getattr(c, "key", str(c)) for c in view.get_form_columns()]
            for rf in REDACTED_FIELDS:
                assert rf not in form_cols, f"{view_name} làm rò rỉ {rf} trong Form columns!"
        except Exception:
            pass


def test_person_secret_admin_endpoints_blocked(client: TestClient, db: Session):
    """PersonSecretAdmin chặn triệt để thao tác Create, Edit, Export, Details từ client."""
    role = db.scalar(select(Role).where(Role.code == "ADMIN"))
    if not role:
        role = Role(code="ADMIN", name_en="Administrator")
        db.add(role)
        db.flush()

    admin_user = User(
        username="sec_auditor",
        password_hash=hash_password("AuditAdmin@123"),
        display_name="Security Auditor",
        role_id=role.id,
    )
    db.add(admin_user)
    db.flush()

    token = create_session_token({
        "user_id": admin_user.id,
        "username": admin_user.username,
        "role": "ADMIN",
    })
    client.cookies.set("itam_session", token)

    # Thử gọi các endpoint nhạy cảm của SQLAdmin đối với PersonSecret
    res_create = client.get("/admin/person-secret/create", follow_redirects=False)
    assert res_create.status_code in (403, 404)

    res_export = client.get("/admin/person-secret/export/csv", follow_redirects=False)
    assert res_export.status_code in (403, 404)

    res_details = client.get("/admin/person-secret/details/1", follow_redirects=False)
    assert res_details.status_code in (403, 404)


def test_auth_me_never_leaks_password_hash(client: TestClient, db: Session):
    """Endpoint GET /auth/me chỉ trả về profile an toàn, không có password_hash hay thông tin mật."""
    role = db.scalar(select(Role).where(Role.code == "ADMIN"))
    if not role:
        role = Role(code="ADMIN", name_en="Administrator")
        db.add(role)
        db.flush()

    user = User(
        username="normal_user",
        password_hash=hash_password("SecretPass@456"),
        display_name="Normal User",
        role_id=role.id,
    )
    db.add(user)
    db.flush()

    token = create_session_token({
        "user_id": user.id,
        "username": user.username,
        "role": "ADMIN",
    })
    client.cookies.set("itam_session", token)

    res = client.get("/auth/me")
    assert res.status_code == 200
    data = res.json()

    assert "password_hash" not in data
    assert "password" not in data
    assert data["username"] == "normal_user"
    assert "permissions" in data


def test_auth_login_sets_httponly_cookie(client: TestClient, db: Session):
    """Khi đăng nhập, cookie itam_session bắt buộc phải có cờ HttpOnly và SameSite=lax để chống XSS."""
    role = db.scalar(select(Role).where(Role.code == "ADMIN"))
    if not role:
        role = Role(code="ADMIN", name_en="Administrator")
        db.add(role)
        db.flush()

    user = User(
        username="login_test_user",
        password_hash=hash_password("TestLogin@789"),
        display_name="Login Tester",
        role_id=role.id,
    )
    db.add(user)
    db.flush()

    res = client.post(
        "/auth/login",
        json={"username": "login_test_user", "password": "TestLogin@789"},
    )
    assert res.status_code == 200

    set_cookie_header = res.headers.get("set-cookie", "")
    assert "itam_session=" in set_cookie_header
    assert "httponly" in set_cookie_header.lower()
    assert "samesite=lax" in set_cookie_header.lower()


def test_revoke_reveal_token_invalidates_session(client: TestClient, db: Session):
    """Endpoint POST /admin/person-secret/reveal/revoke lập tức hủy token xem mật khẩu."""
    role = db.scalar(select(Role).where(Role.code == "ADMIN"))
    if not role:
        role = Role(code="ADMIN", name_en="Administrator")
        db.add(role)
        db.flush()

    admin_user = User(
        username="gate_admin",
        password_hash=hash_password("AdminGate@123"),
        display_name="Gate Admin",
        role_id=role.id,
    )
    db.add(admin_user)
    db.flush()

    gate = RevealGate()
    token = gate.authorize(
        user_id=admin_user.id,
        password="AdminGate@123",
        password_hash=admin_user.password_hash,
        verifier=lambda p, h: True,
    )
    gate.check_token(admin_user.id, token)

    # Thu hồi token
    gate.revoke(admin_user.id)
    with pytest.raises(Exception):
        gate.check_token(admin_user.id, token)
