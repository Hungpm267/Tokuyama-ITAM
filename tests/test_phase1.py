"""Bộ kiểm thử Giai đoạn 1: Security (Argon2id), RBAC 3 vai trò, Audit Log, Đăng nhập, SQLAdmin.

Yêu cầu theo GEMINI.md:
- Test RBAC cho cả 3 vai trò (ADMIN, GA_MANAGER, EXECUTIVE) phải xanh.
- Mật khẩu nhân viên / nhạy cảm không bao giờ lọt vào audit log.
- SQLAdmin chỉ cho phép tài khoản vai trò ADMIN truy cập.
- AuditLog là bảng bất biến và chỉ thêm.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import audit_login, record_audit, sanitize_dict
from app.core.permissions import has_permission
from app.core.security import (
    hash_password,
    verify_password,
    create_session_token,
    verify_session_token,
)
from app.enums import AuditAction, Module, PermissionAction, RoleCode, DEFAULT_ROLE_PERMISSIONS
from app.db import get_db
from app.main import app
from app.models import AuditLog, Role, RolePermission, User, UserPermissionOverride


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

    admin = getattr(app.state, "admin", None)
    if admin:
        monkeypatch.setattr(admin, "session_maker", mock_maker)
        for view in admin._views:
            monkeypatch.setattr(view, "session_maker", mock_maker)

    yield
    app.dependency_overrides.clear()


# --------------------------------------------------------------------------
# 1. BẢO MẬT & BĂM MẬT KHẨU ARGON2ID
# --------------------------------------------------------------------------

def test_argon2id_hash_and_verification():
    raw_pass = "P@ssw0rdTokuyama2026!"
    hashed = hash_password(raw_pass)

    assert hashed.startswith("$argon2id$")
    assert verify_password(raw_pass, hashed) is True
    assert verify_password("wrong_password", hashed) is False
    assert verify_password("", hashed) is False
    assert verify_password(raw_pass, "corrupted_hash") is False


def test_argon2id_empty_password_rejected():
    with pytest.raises(ValueError, match="không được để trống"):
        hash_password("")


def test_session_token_lifecycle():
    data = {"user_id": 1, "username": "it.admin", "role": "ADMIN"}
    token = create_session_token(data)

    payload = verify_session_token(token, max_age_seconds=60)
    assert payload is not None
    assert payload["user_id"] == 1
    assert payload["username"] == "it.admin"
    assert payload["role"] == "ADMIN"

    # Token bị làm giả / sửa đổi
    tampered_token = token + "bad"
    assert verify_session_token(tampered_token) is None
    assert verify_session_token("") is None


# --------------------------------------------------------------------------
# 2. AUDIT LOG & LOẠI TRỪ DỮ LIỆU NHẠY CẢM (REDACTED_FIELDS)
# --------------------------------------------------------------------------

def test_audit_sanitization_removes_sensitive_fields():
    dirty_data = {
        "id": 10,
        "username": "tanaka",
        "password_hash": "$argon2id$v=19$m=65536,t=2,p=1$secret_hash",
        "pc_password_enc": b"encrypted_bytes_here",
        "email_password_enc": b"encrypted_email_bytes",
        "license_key_enc": b"encrypted_lic_bytes",
        "my_secret_token": "abc",
        "remarks": "Clean normal remark",
    }
    clean = sanitize_dict(dirty_data)

    assert clean["id"] == 10
    assert clean["username"] == "tanaka"
    assert clean["remarks"] == "Clean normal remark"
    assert clean["password_hash"] == "[REDACTED]"
    assert clean["pc_password_enc"] == "[REDACTED]"
    assert clean["email_password_enc"] == "[REDACTED]"
    assert clean["license_key_enc"] == "[REDACTED]"


def test_record_audit_in_database(db: Session, seed):
    user = seed["user"]
    log = record_audit(
        db=db,
        action=AuditAction.CREATE,
        table_name="assets",
        record_id=101,
        user_id=user.id,
        before=None,
        after={"serial": "SN-9999", "password_hash": "should_be_hidden"},
        ip_address="192.168.1.50",
    )
    db.flush()

    assert log.id is not None
    assert log.action == AuditAction.CREATE
    assert log.table_name == "assets"
    assert log.record_id == 101
    assert log.user_id == user.id
    assert log.before_after["after"]["serial"] == "SN-9999"
    assert log.before_after["after"]["password_hash"] == "[REDACTED]"


def test_audit_login_events(db: Session, seed):
    user = seed["user"]
    log_success = audit_login(db, user_id=user.id, success=True, username=user.username, ip_address="10.0.0.1")
    log_fail = audit_login(db, user_id=None, success=False, username="unknown_attacker", ip_address="10.0.0.2")
    db.flush()

    assert log_success.action == AuditAction.LOGIN
    assert log_success.user_id == user.id

    assert log_fail.action == AuditAction.LOGIN_FAIL
    assert log_fail.user_id is None
    assert log_fail.before_after["extra"]["username"] == "unknown_attacker"


# --------------------------------------------------------------------------
# 3. PHÂN QUYỀN RBAC CHO CẢ 3 VAI TRÒ
# --------------------------------------------------------------------------

@pytest.fixture
def rbac_roles_and_users(db: Session):
    """Tạo 3 vai trò và 3 user đại diện cho 3 vai trò theo ma trận quyền DEFAULT_ROLE_PERMISSIONS."""
    roles = {}
    for code, modules in DEFAULT_ROLE_PERMISSIONS.items():
        role = Role(code=code.value, name_en=code.value, name_ja=code.value)
        db.add(role)
        db.flush()
        roles[code] = role

        for mod, actions in modules.items():
            for act in actions:
                db.add(
                    RolePermission(role_id=role.id, module=mod.value, action=act.value)
                )
        db.flush()

    admin_user = User(
        username="admin_user",
        password_hash=hash_password("admin_pass_123"),
        display_name="Admin Toku",
        role_id=roles[RoleCode.ADMIN].id,
    )
    ga_user = User(
        username="ga_user",
        password_hash=hash_password("ga_pass_123"),
        display_name="GA Manager Toku",
        role_id=roles[RoleCode.GA_MANAGER].id,
    )
    exec_user = User(
        username="exec_user",
        password_hash=hash_password("exec_pass_123"),
        display_name="Executive Director",
        role_id=roles[RoleCode.EXECUTIVE].id,
    )
    db.add_all([admin_user, ga_user, exec_user])
    db.flush()

    return {
        "roles": roles,
        "admin": admin_user,
        "ga": ga_user,
        "exec": exec_user,
    }


def test_rbac_admin_has_full_permissions(db: Session, rbac_roles_and_users):
    admin = rbac_roles_and_users["admin"]

    # Admin có đủ 4 action trên tất cả các module
    assert has_permission(db, admin, Module.PERSONS, PermissionAction.VIEW) is True
    assert has_permission(db, admin, Module.PERSONS, PermissionAction.ADD) is True
    assert has_permission(db, admin, Module.PERSONS, PermissionAction.CHANGE) is True
    assert has_permission(db, admin, Module.PERSONS, PermissionAction.DELETE) is True
    assert has_permission(db, admin, Module.SECRETS, PermissionAction.VIEW) is True
    assert has_permission(db, admin, Module.USERS, PermissionAction.CHANGE) is True


def test_rbac_ga_manager_permissions(db: Session, rbac_roles_and_users):
    ga = rbac_roles_and_users["ga"]

    # GA Manager có view/add/change/delete trên thẻ cards
    assert has_permission(db, ga, Module.CARDS, PermissionAction.VIEW) is True
    assert has_permission(db, ga, Module.CARDS, PermissionAction.ADD) is True
    assert has_permission(db, ga, Module.CARDS, PermissionAction.CHANGE) is True
    assert has_permission(db, ga, Module.CARDS, PermissionAction.DELETE) is True

    # GA Manager có view/add/change trên nhân sự persons, nhưng KHÔNG có delete
    assert has_permission(db, ga, Module.PERSONS, PermissionAction.VIEW) is True
    assert has_permission(db, ga, Module.PERSONS, PermissionAction.ADD) is True
    assert has_permission(db, ga, Module.PERSONS, PermissionAction.CHANGE) is True
    assert has_permission(db, ga, Module.PERSONS, PermissionAction.DELETE) is False

    # GA Manager chỉ có VIEW trên assets và contracts
    assert has_permission(db, ga, Module.ASSETS, PermissionAction.VIEW) is True
    assert has_permission(db, ga, Module.ASSETS, PermissionAction.ADD) is False
    assert has_permission(db, ga, Module.CONTRACTS, PermissionAction.VIEW) is True
    assert has_permission(db, ga, Module.CONTRACTS, PermissionAction.ADD) is False

    # GA Manager KHÔNG CÓ QUYỀN trên secrets, users, audit
    assert has_permission(db, ga, Module.SECRETS, PermissionAction.VIEW) is False
    assert has_permission(db, ga, Module.USERS, PermissionAction.VIEW) is False
    assert has_permission(db, ga, Module.AUDIT, PermissionAction.VIEW) is False


def test_rbac_executive_read_only_permissions(db: Session, rbac_roles_and_users):
    exec_user = rbac_roles_and_users["exec"]

    # Executive chỉ có VIEW trên các bảng báo cáo
    assert has_permission(db, exec_user, Module.ASSETS, PermissionAction.VIEW) is True
    assert has_permission(db, exec_user, Module.LICENSES, PermissionAction.VIEW) is True
    assert has_permission(db, exec_user, Module.CONTRACTS, PermissionAction.VIEW) is True
    assert has_permission(db, exec_user, Module.AUDIT, PermissionAction.VIEW) is True

    # Executive KHÔNG có bất kỳ quyền ADD, CHANGE, DELETE nào
    assert has_permission(db, exec_user, Module.ASSETS, PermissionAction.ADD) is False
    assert has_permission(db, exec_user, Module.ASSETS, PermissionAction.CHANGE) is False
    assert has_permission(db, exec_user, Module.ASSETS, PermissionAction.DELETE) is False
    assert has_permission(db, exec_user, Module.CARDS, PermissionAction.ADD) is False

    # Executive KHÔNG có quyền trên secrets hay users
    assert has_permission(db, exec_user, Module.SECRETS, PermissionAction.VIEW) is False
    assert has_permission(db, exec_user, Module.USERS, PermissionAction.VIEW) is False


def test_rbac_user_permission_overrides(db: Session, rbac_roles_and_users):
    ga = rbac_roles_and_users["ga"]
    admin = rbac_roles_and_users["admin"]

    # Ban đầu GA không có quyền xem Audit
    assert has_permission(db, ga, Module.AUDIT, PermissionAction.VIEW) is False

    # Cấp override cho GA được xem Audit
    override_grant = UserPermissionOverride(
        user_id=ga.id,
        module=Module.AUDIT.value,
        action=PermissionAction.VIEW.value,
        granted=True,
    )
    db.add(override_grant)
    db.flush()

    # Sau override, GA xem được Audit
    assert has_permission(db, ga, Module.AUDIT, PermissionAction.VIEW) is True

    # Thu hồi override từ Admin (ví dụ thu hồi quyền xoá Users)
    override_revoke = UserPermissionOverride(
        user_id=admin.id,
        module=Module.USERS.value,
        action=PermissionAction.DELETE.value,
        granted=False,
    )
    db.add(override_revoke)
    db.flush()

    assert has_permission(db, admin, Module.USERS, PermissionAction.DELETE) is False


# --------------------------------------------------------------------------
# 4. API AUTH FLOW & ĐĂNG NHẬP
# --------------------------------------------------------------------------

def test_api_login_success_and_logout(db: Session, rbac_roles_and_users):
    admin = rbac_roles_and_users["admin"]
    client = TestClient(app)

    # Đăng nhập hợp lệ
    res = client.post("/auth/login", json={"username": admin.username, "password": "admin_pass_123"})
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert data["user"]["username"] == admin.username
    assert "token" in data
    assert "itam_session" in res.cookies

    # Gọi /auth/me với cookie phiên
    res_me = client.get("/auth/me")
    assert res_me.status_code == 200
    me_data = res_me.json()
    assert me_data["username"] == admin.username
    assert me_data["role"] == "ADMIN"
    assert len(me_data["permissions"]) > 0

    # Đăng xuất
    res_logout = client.post("/auth/logout")
    assert res_logout.status_code == 200


def test_api_login_failure(db: Session, rbac_roles_and_users):
    admin = rbac_roles_and_users["admin"]
    client = TestClient(app)

    # Mật khẩu sai
    res = client.post("/auth/login", json={"username": admin.username, "password": "wrong_password"})
    assert res.status_code == 401
    assert "không chính xác" in res.json()["detail"]


# --------------------------------------------------------------------------
# 5. SQLADMIN ACCESS CONTROL (CHỈ ADMIN MỚI VÀO ĐƯỢC)
# --------------------------------------------------------------------------

def test_sqladmin_only_accessible_by_admin(db: Session, rbac_roles_and_users):
    admin = rbac_roles_and_users["admin"]
    ga = rbac_roles_and_users["ga"]
    
    # 1. Client của Admin
    client_admin = TestClient(app)
    admin_token = create_session_token({"user_id": admin.id, "role": "ADMIN", "username": admin.username})
    client_admin.cookies.set("itam_session", admin_token)
    res_admin = client_admin.get("/admin/", follow_redirects=False)
    assert res_admin.status_code == 200
    assert "Tokuyama IT Portal" in res_admin.text

    # 2. Client của GA Manager -> Bị chặn (Redirect về /admin/login do không phải ADMIN)
    client_ga = TestClient(app)
    ga_token = create_session_token({"user_id": ga.id, "role": "GA_MANAGER", "username": ga.username})
    client_ga.cookies.set("itam_session", ga_token)
    res_ga = client_ga.get("/admin/", follow_redirects=False)
    assert res_ga.status_code in (302, 307)
    assert "/admin/login" in res_ga.headers.get("location", "")


def test_sqladmin_soft_delete_and_protections(db: Session, rbac_roles_and_users):
    admin = rbac_roles_and_users["admin"]
    exec_user = rbac_roles_and_users["exec"]

    client = TestClient(app)
    admin_token = create_session_token({"user_id": admin.id, "role": "ADMIN", "username": admin.username})
    client.cookies.set("itam_session", admin_token)

    # 1. Thử tự xóa tài khoản admin đang đăng nhập -> Bị chặn 400
    res_self = client.delete(f"/admin/user/delete?pks={admin.id}")
    assert res_self.status_code == 400
    assert "chính bạn" in res_self.text

    # 2. Xóa tài khoản exec_user -> Thành công, chuyển thành xóa mềm
    res_del = client.delete(f"/admin/user/delete?pks={exec_user.id}&delete_reason=Nghi+viec")
    assert res_del.status_code == 200

    # Kiểm tra DB: exec_user phải có is_deleted = True, deleted_at, deleted_by, delete_reason
    db.refresh(exec_user)
    assert exec_user.is_deleted is True
    assert exec_user.deleted_at is not None
    assert exec_user.deleted_by == admin.id
    assert exec_user.delete_reason == "Nghi viec"

    # Kiểm tra Audit Log: phải có log DELETE cho bảng users
    audit_del = db.scalar(
        select(AuditLog).where(
            AuditLog.table_name == "users",
            AuditLog.record_id == exec_user.id,
            AuditLog.action == AuditAction.DELETE,
        )
    )
    assert audit_del is not None
    assert audit_del.user_id == admin.id

    # 3. Danh sách /admin/user/list không được hiển thị exec_user đã xóa
    res_list = client.get("/admin/user/list")
    assert res_list.status_code == 200
    assert exec_user.username not in res_list.text

    # 4. Kiểm tra các bảng lịch sử không cho phép xóa (can_delete = False)
    from app.admin import AssignmentAdmin, LicenseAssignmentAdmin, CardLoanAdmin, AuditLogAdmin
    assert AssignmentAdmin.can_delete is False
    assert LicenseAssignmentAdmin.can_delete is False
    assert CardLoanAdmin.can_delete is False
    assert AuditLogAdmin.can_delete is False


def test_sqladmin_user_create_with_password(db: Session, rbac_roles_and_users):
    admin = rbac_roles_and_users["admin"]
    client = TestClient(app)
    admin_token = create_session_token({"user_id": admin.id, "role": "ADMIN", "username": admin.username})
    client.cookies.set("itam_session", admin_token)

    # 1. Mở trang tạo user -> Có ô password, không có last_login_at
    res_get = client.get("/admin/user/create")
    assert res_get.status_code == 200
    assert "password" in res_get.text
    assert "last_login_at" not in res_get.text

    # 2. Tạo user không nhập password -> Bị chặn báo lỗi
    res_empty_pwd = client.post("/admin/user/create", data={
        "role": str(admin.role_id),
        "username": "tomo_new",
        "display_name": "Tomo New",
        "preferred_lang": "en",
        "is_active": "true",
        "password": "",
    })
    assert res_empty_pwd.status_code in (200, 400)
    assert "mật khẩu" in res_empty_pwd.text.lower() or "password" in res_empty_pwd.text.lower()

    # 3. Tạo user có mật khẩu hợp lệ -> Thành công, băm Argon2id
    res_create = client.post("/admin/user/create", data={
        "role": str(admin.role_id),
        "username": "tomo_new",
        "display_name": "Tomo New",
        "preferred_lang": "en",
        "is_active": "true",
        "password": "SecretPassword123!",
    }, follow_redirects=False)
    assert res_create.status_code in (200, 302)

    new_user = db.scalar(select(User).where(User.username == "tomo_new"))
    assert new_user is not None
    assert new_user.display_name == "Tomo New"
    assert verify_password("SecretPassword123!", new_user.password_hash) is True

    # 4. Sửa user mà để trống password -> Giữ nguyên mật khẩu cũ
    res_edit_same = client.post(f"/admin/user/edit/{new_user.id}", data={
        "role": str(admin.role_id),
        "username": "tomo_new",
        "display_name": "Tomo New Updated",
        "preferred_lang": "vi",
        "is_active": "true",
        "password": "",
    }, follow_redirects=False)
    assert res_edit_same.status_code in (200, 302)

    db.refresh(new_user)
    assert new_user.display_name == "Tomo New Updated"
    assert verify_password("SecretPassword123!", new_user.password_hash) is True

    # 5. Sửa user với mật khẩu mới -> Băm mật khẩu mới
    res_edit_new_pwd = client.post(f"/admin/user/edit/{new_user.id}", data={
        "role": str(admin.role_id),
        "username": "tomo_new",
        "display_name": "Tomo New Updated",
        "preferred_lang": "vi",
        "is_active": "true",
        "password": "NewSecretPassword456!",
    }, follow_redirects=False)
    assert res_edit_new_pwd.status_code in (200, 302)

    db.refresh(new_user)
    assert verify_password("NewSecretPassword456!", new_user.password_hash) is True


def test_sqladmin_relation_list_views(db: Session, rbac_roles_and_users):
    admin = rbac_roles_and_users["admin"]
    client = TestClient(app)
    admin_token = create_session_token({"user_id": admin.id, "role": "ADMIN", "username": admin.username})
    client.cookies.set("itam_session", admin_token)

    for path in [
        "/admin/license-assignment/list",
        "/admin/license/list",
        "/admin/assignment/list",
        "/admin/card-loan/list",
    ]:
        res = client.get(path)
        assert res.status_code == 200


