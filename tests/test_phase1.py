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

def test_sqladmin_unified_portal_rbac(db: Session, rbac_roles_and_users):
    admin = rbac_roles_and_users["admin"]
    ga = rbac_roles_and_users["ga"]
    exec_user = rbac_roles_and_users["exec"]

    # 1. Chưa đăng nhập -> Chuyển hướng về /admin/login
    client_anon = TestClient(app)
    res_anon = client_anon.get("/admin/", follow_redirects=False)
    assert res_anon.status_code in (302, 307)
    assert "/admin/login" in res_anon.headers.get("location", "")

    # 2. Client của Admin -> Vào được /admin/ và các bảng bảo mật
    client_admin = TestClient(app)
    admin_token = create_session_token({"user_id": admin.id, "role": "ADMIN", "username": admin.username})
    client_admin.cookies.set("itam_session", admin_token)
    res_admin = client_admin.get("/admin/", follow_redirects=False)
    assert res_admin.status_code == 200
    assert "Tokuyama IT Portal" in res_admin.text

    res_admin_users = client_admin.get("/admin/user/list", follow_redirects=False)
    assert res_admin_users.status_code == 200

    # 3. Client của GA Manager -> Vào được /admin/, nhưng bị 403 ở Users và PersonSecrets
    client_ga = TestClient(app)
    ga_token = create_session_token({"user_id": ga.id, "role": "GA_MANAGER", "username": ga.username})
    client_ga.cookies.set("itam_session", ga_token)
    res_ga = client_ga.get("/admin/", follow_redirects=False)
    assert res_ga.status_code == 200

    res_ga_users = client_ga.get("/admin/user/list", follow_redirects=False)
    assert res_ga_users.status_code == 403

    res_ga_secrets = client_ga.get("/admin/person-secret/list", follow_redirects=False)
    assert res_ga_secrets.status_code == 403

    # GA Manager vào được Person list
    res_ga_persons = client_ga.get("/admin/person/list", follow_redirects=False)
    assert res_ga_persons.status_code == 200

    # 4. Client của Executive -> Vào được /admin/, nhưng bị 403 ở Users và Create Asset
    client_exec = TestClient(app)
    exec_token = create_session_token({"user_id": exec_user.id, "role": "EXECUTIVE", "username": exec_user.username})
    client_exec.cookies.set("itam_session", exec_token)
    res_exec = client_exec.get("/admin/", follow_redirects=False)
    assert res_exec.status_code == 200

    res_exec_users = client_exec.get("/admin/user/list", follow_redirects=False)
    assert res_exec_users.status_code == 403

    # Executive chỉ có quyền View, không có quyền Add
    res_exec_add_asset = client_exec.get("/admin/asset/create", follow_redirects=False)
    assert res_exec_add_asset.status_code == 403

    # 5. Đăng xuất SQLAdmin -> Xoá cookie và redirect về /admin/login
    res_logout = client_admin.get("/admin/logout", follow_redirects=False)
    assert res_logout.status_code in (302, 307)
    assert "/admin/login" in res_logout.headers.get("location", "")
    assert "itam_session" in res_logout.headers.get("set-cookie", "")


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


def test_card_borrowed_workflow_and_sync(db: Session, rbac_roles_and_users):
    from app.enums import CardStatus
    from app.models import AccessCard, CardLoan

    admin = rbac_roles_and_users["admin"]
    client = TestClient(app)
    admin_token = create_session_token({"user_id": admin.id, "role": "ADMIN", "username": admin.username})
    client.cookies.set("itam_session", admin_token)

    # 1. Chặn tạo thẻ với status BORROWED
    res_fail = client.post("/admin/access-card/create", data={
        "card_no": "TEST_CARD_SYNC_01",
        "card_type": "GUEST",
        "status": "BORROWED",
    })
    assert res_fail.status_code == 400
    assert "BORROWED" in res_fail.text

    # 2. Tạo thẻ hợp lệ với IN_STOCK
    res_ok = client.post("/admin/access-card/create", data={
        "card_no": "TEST_CARD_SYNC_01",
        "card_type": "GUEST",
        "status": "IN_STOCK",
    }, follow_redirects=True)
    assert res_ok.status_code == 200

    card = db.scalar(select(AccessCard).where(AccessCard.card_no == "TEST_CARD_SYNC_01"))
    assert card is not None
    assert card.status == CardStatus.IN_STOCK
    assert card.current_borrower is None

    # 3. Tạo phiếu mượn thẻ -> Card tự động chuyển sang BORROWED
    res_loan = client.post("/admin/card-loan/create", data={
        "card": str(card.id),
        "external_name": "Nguyen Van Khach",
        "external_company": "Nha thau Son",
        "borrowed_at": "2026-10-07",
    }, follow_redirects=True)
    assert res_loan.status_code == 200

    db.refresh(card)
    assert card.status == CardStatus.BORROWED
    assert "Nguyen Van Khach" in card.current_borrower

    # 4. Kiểm tra trang danh sách thẻ hiển thị cột Người đang giữ thẻ
    res_list = client.get("/admin/access-card/list")
    assert res_list.status_code == 200
    assert "Nguyen Van Khach" in res_list.text

    # 5. Trả thẻ -> Card tự động về IN_STOCK
    loan = db.scalar(select(CardLoan).where(CardLoan.card_id == card.id, CardLoan.returned_at.is_(None)))
    assert loan is not None
    res_return = client.post(f"/admin/card-loan/edit/{loan.id}", data={
        "card": str(card.id),
        "external_name": "Nguyen Van Khach",
        "external_company": "Nha thau Son",
        "borrowed_at": "2026-10-07",
        "returned_at": "2026-10-07",
    }, follow_redirects=True)
    assert res_return.status_code == 200

    db.refresh(card)
    assert card.status == CardStatus.IN_STOCK
    assert card.current_borrower is None


def test_save_redirects_and_admin_password_change(db: Session, rbac_roles_and_users):
    admin = rbac_roles_and_users["admin"]
    client = TestClient(app)
    admin_token = create_session_token({"user_id": admin.id, "role": "ADMIN", "username": admin.username})
    client.cookies.set("itam_session", admin_token)

    # 1. Bấm 'Save' / 'Lưu' trên form create phải redirect về list
    res_save = client.post("/admin/access-card/create", data={
        "card_no": "TEST_CARD_SAVE_LIST",
        "card_type": "STAFF",
        "status": "IN_STOCK",
        "save": "Lưu",
    }, follow_redirects=False)
    assert res_save.status_code == 302
    assert "/admin/access-card/list" in res_save.headers.get("location", "")

    # 2. Bấm 'Lưu và thêm mới' trên form create phải redirect về create
    res_add_another = client.post("/admin/access-card/create", data={
        "card_no": "TEST_CARD_ADD_ANOTHER",
        "card_type": "STAFF",
        "status": "IN_STOCK",
        "save": "Lưu và thêm mới",
    }, follow_redirects=False)
    assert res_add_another.status_code == 302
    assert "/admin/access-card/create" in res_add_another.headers.get("location", "")

    # 3. Admin đổi mật khẩu cho user khác -> thành công và redirect về /admin/user/list
    ga_user = rbac_roles_and_users["ga"]
    res_change_pwd = client.post(f"/admin/user/edit/{ga_user.id}", data={
        "role": str(ga_user.role_id),
        "username": ga_user.username,
        "display_name": ga_user.display_name,
        "password": "NewGaPassword123!",
        "save": "Lưu thay đổi",
    }, follow_redirects=False)
    assert res_change_pwd.status_code == 302
    assert "/admin/user/list" in res_change_pwd.headers.get("location", "")

    db.refresh(ga_user)
    assert verify_password("NewGaPassword123!", ga_user.password_hash) is True


def test_audit_trail_features_and_delete_reason(db: Session, rbac_roles_and_users):
    """Kiểm tra toàn diện tính năng Audit Trail:
    - Xóa bản ghi ghi nhận đúng delete_reason vào audit log và summary
    - Lọc (filter) theo action, table và sắp xếp (sort) trên danh sách
    - Xem chi tiết audit log định dạng thân thiện (không raw JSON)
    """
    from app.models import AuditLog, User
    from app.enums import AuditAction

    admin = rbac_roles_and_users["admin"]
    client = TestClient(app)
    admin_token = create_session_token({"user_id": admin.id, "role": "ADMIN", "username": admin.username})
    client.cookies.set("itam_session", admin_token)

    # 1. Tạo một user thử nghiệm để xóa
    temp_user = User(
        username="temp_user_for_delete",
        password_hash=hash_password("TempPass123!"),
        role_id=admin.role_id,
        display_name="Temporary User",
        is_active=True,
    )
    db.add(temp_user)
    db.commit()
    db.refresh(temp_user)

    # 2. Xóa user với lý do xóa cụ thể
    del_reason = "Nghi viec va ban giao xong"
    res_del = client.delete(f"/admin/user/delete?pks={temp_user.id}&delete_reason={del_reason.replace(' ', '+')}")
    assert res_del.status_code == 200

    # 3. Kiểm tra AuditLog được tạo trong DB
    audit = db.scalar(
        select(AuditLog)
        .where(
            AuditLog.table_name == "users",
            AuditLog.record_id == temp_user.id,
            AuditLog.action == AuditAction.DELETE,
        )
        .order_by(AuditLog.id.desc())
    )
    assert audit is not None
    assert audit.before_after is not None
    assert audit.before_after.get("extra", {}).get("delete_reason") == del_reason
    assert del_reason in audit.summary

    # 4. Kiểm tra trang danh sách Audit Trail có hiển thị summary lý do xóa và các thanh lọc / sắp xếp
    res_list = client.get("/admin/audit-log/list")
    assert res_list.status_code == 200
    assert del_reason in res_list.text

    # Lọc theo action=DELETE và table=users
    res_filtered = client.get("/admin/audit-log/list?action=DELETE&table=users&sortBy=created_at&sort=desc")
    assert res_filtered.status_code == 200
    assert del_reason in res_filtered.text

    # 5. Kiểm tra trang xem chi tiết Audit Log
    res_detail = client.get(f"/admin/audit-log/details/{audit.id}")
    assert res_detail.status_code == 200
    # Phải có khối cảnh báo lý do xóa
    assert del_reason in res_detail.text
    # Phải có bảng cấu trúc hiển thị thông tin thay vì JSON thô
    assert "temp_user_for_delete" in res_detail.text
    # Phải có khối JSON kỹ thuật thu gọn
    assert "technical JSON" in res_detail.text or "kỹ thuật" in res_detail.text


def test_role_permission_matrix_workflow(db: Session, rbac_roles_and_users):
    """Kiểm tra toàn diện tính năng Ma trận Quyền Vai trò:
    - Giao diện ma trận trực quan (interactive matrix view)
    - Chế độ dữ liệu thô (raw mode)
    - Chặn người dùng không phải Admin gọi API thay đổi ma trận (403)
    - Admin lưu ma trận thành công và tạo AuditLog
    - Admin khôi phục quyền mặc định (reset to defaults) thành công
    """
    from app.models import AuditLog, Role
    from app.enums import AuditAction
    from app.db import get_db

    admin = rbac_roles_and_users["admin"]
    ga_user = rbac_roles_and_users["ga"]
    ga_role = rbac_roles_and_users[RoleCode.GA_MANAGER] if RoleCode.GA_MANAGER in rbac_roles_and_users else db.scalar(select(Role).where(Role.code == "GA_MANAGER"))
    db.commit()

    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        admin_token = create_session_token({"user_id": admin.id, "role": "ADMIN", "username": admin.username})
        ga_token = create_session_token({"user_id": ga_user.id, "role": "GA_MANAGER", "username": ga_user.username})

        # 1. Non-admin không được lưu ma trận (403)
        client.cookies.set("itam_session", ga_token)
        res_ga_save = client.post("/admin/role-permission/matrix/save", json={
            "role_id": ga_role.id,
            "permissions": [{"module": "persons", "action": "view"}]
        })
        assert res_ga_save.status_code == 403

        # 2. Admin truy cập trang Ma trận Quyền Vai trò -> 200 OK với giao diện Matrix
        client.cookies.set("itam_session", admin_token)
        res_matrix = client.get("/admin/role-permission/list")
        assert res_matrix.status_code == 200
        assert "Ma trận Quyền Vai trò" in res_matrix.text
        assert "perm-cb" in res_matrix.text
        assert "GA_MANAGER" in res_matrix.text
        assert "ADMIN" in res_matrix.text

        # 3. Chế độ dữ liệu thô (mode=raw) -> 200 OK
        res_raw = client.get("/admin/role-permission/list?mode=raw")
        assert res_raw.status_code == 200
        assert "Chế độ dữ liệu thô" in res_raw.text or "Raw mode" in res_raw.text

        # 4. Admin lưu ma trận quyền cho vai trò GA_MANAGER
        res_save = client.post("/admin/role-permission/matrix/save", json={
            "role_id": ga_role.id,
            "permissions": [
                {"module": "persons", "action": "view"},
                {"module": "assets", "action": "view"},
                {"module": "cards", "action": "view"},
                {"module": "cards", "action": "add"},
            ]
        })
        assert res_save.status_code == 200, f"res_save failed: {res_save.status_code} - {res_save.text}"
        assert res_save.json().get("success") is True
        assert res_save.json().get("total") == 4

        # Kiểm tra AuditLog được tạo
        save_audit = db.scalar(
            select(AuditLog)
            .where(
                AuditLog.table_name == "role_permissions",
                AuditLog.record_id == ga_role.id,
                AuditLog.action == AuditAction.UPDATE,
            )
            .order_by(AuditLog.id.desc())
        )
        assert save_audit is not None
        assert save_audit.user_id == admin.id
        assert save_audit.before_after is not None

        # 5. Khôi phục mặc định cho vai trò GA_MANAGER
        res_reset = client.post("/admin/role-permission/matrix/reset", json={"role_id": ga_role.id})
        assert res_reset.status_code == 200
        assert res_reset.json().get("success") is True
        # GA Manager mặc định có 13 quyền
        assert res_reset.json().get("total") == 13
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_details_view_human_friendly_labels(db: Session, rbac_roles_and_users):
    """Kiểm tra màn hình Chi tiết (Details View) và Danh sách (List View):
    - Không hiển thị tên thuộc tính dạng database column name (như code, name_en, is_deleted, created_at...)
    - Hiển thị nhãn tiếng Việt rõ ràng, thân thiện với người dùng
    - Hiển thị song ngữ chính xác khi chuyển đổi ngôn ngữ (lang=en)
    - Phân tách khu vực nghiệp vụ và 'Thông tin hệ thống & Kiểm toán'
    - Trạng thái xóa hiển thị badge thân thiện ('Đang hoạt động') thay vì biểu tượng kỹ thuật
    """
    from app.models import Department, AccessCard

    admin = rbac_roles_and_users["admin"]
    admin.preferred_lang = "vi"
    db.commit()

    client = TestClient(app)
    admin_token = create_session_token({"user_id": admin.id, "role": "ADMIN", "username": admin.username})
    client.cookies.set("itam_session", admin_token)
    client.cookies.set("itam_lang", "vi")

    # 1. Tạo dữ liệu mẫu phòng ban
    dept = Department(code="TVC-TEST-DEPT", name_en="Phòng CNTT Thử nghiệm", name_ja="IT部門")
    db.add(dept)
    db.commit()
    db.refresh(dept)

    # 2. Kiểm tra xem chi tiết Phòng ban tiếng Việt
    res_vi = client.get(f"/admin/department/details/{dept.id}?lang=vi")
    assert res_vi.status_code == 200
    text_vi = res_vi.text

    # Phải có các nhãn tiếng Việt thân thiện
    assert "Mã phòng ban" in text_vi
    assert "Tên phòng ban (Tiếng Anh/Việt)" in text_vi
    assert "Tên phòng ban (Tiếng Nhật)" in text_vi
    assert "Thời gian tạo" in text_vi
    assert "Thời gian cập nhật" in text_vi
    assert "Trạng thái xóa" in text_vi
    assert "Thông tin hệ thống &amp; Kiểm toán" in text_vi or "Thông tin hệ thống & Kiểm toán" in text_vi
    assert "Đang hoạt động (Chưa xóa)" in text_vi

    # Không được có raw table cell với text là tên cột trần
    assert '>code<' not in text_vi
    assert '>name_en<' not in text_vi
    assert '>name_ja<' not in text_vi
    assert '>is_deleted<' not in text_vi

    # 3. Kiểm tra xem chi tiết Phòng ban tiếng Anh
    res_en = client.get(f"/admin/department/details/{dept.id}?lang=en")
    assert res_en.status_code == 200
    text_en = res_en.text

    assert "Department Code" in text_en
    assert "Department Name (EN/VI)" in text_en
    assert "Department Name (JA)" in text_en
    assert "Created At" in text_en
    assert "Updated At" in text_en
    assert "System &amp; Audit Metadata" in text_en or "System & Audit Metadata" in text_en
    assert "Active (Not Deleted)" in text_en

    # 4. Kiểm tra xem chi tiết Thẻ từ
    card = AccessCard(card_no="CARD-TEST-DETAIL", card_type="STAFF", status="IN_STOCK")
    db.add(card)
    db.commit()
    db.refresh(card)

    res_card = client.get(f"/admin/access-card/details/{card.id}?lang=vi")
    assert res_card.status_code == 200
    assert "Mã số thẻ từ" in res_card.text
    assert "Phân loại thẻ" in res_card.text
    assert "Trạng thái thẻ" in res_card.text
    assert '>card_no<' not in res_card.text
    assert '>card_type<' not in res_card.text


def test_card_loan_overlap_validation(db: Session):
    """Kiểm tra chặn mượn thẻ khi thời gian mượn bị trùng lấn (overlap)."""
    import asyncio
    import datetime as dt
    from unittest.mock import MagicMock
    from app.admin import CardLoanAdmin
    from app.models import AccessCard, CardLoan

    card = AccessCard(card_no="CARD-OVERLAP-1", card_type="STAFF", status="IN_STOCK")
    db.add(card)
    db.commit()
    db.refresh(card)

    # Loan 1: 08/07/2026 -> 07/10/2026
    l1 = CardLoan(card_id=card.id, borrowed_at=dt.date(2026, 7, 8), returned_at=dt.date(2026, 10, 7), external_name="User A")
    db.add(l1)
    db.commit()

    admin = CardLoanAdmin()
    req = MagicMock()
    req.session = {"lang": "vi"}

    # Thử tạo Loan 2: 04/10/2026 (trùng lấn với Loan 1 tới 07/10 mới trả)
    data = {
        "card": card,
        "borrowed_at": dt.date(2026, 10, 4),
        "external_name": "User B",
    }
    with pytest.raises(ValueError, match="Trùng lặp thời gian mượn thẻ"):
        asyncio.run(admin.on_model_change(data, CardLoan(), is_created=True, request=req))


def test_assignment_overlap_validation(db: Session):
    """Kiểm tra chặn cấp phát thiết bị khi thời gian cấp phát bị trùng lấn (overlap)."""
    import asyncio
    import datetime as dt
    from unittest.mock import MagicMock
    from app.admin import AssignmentAdmin
    from app.models import Asset, AssetCategory, Assignment, Person

    cat = AssetCategory(name_en="Laptop Test", name_ja="Laptop Test")
    db.add(cat)
    db.commit()
    db.refresh(cat)

    person = Person(staff_code="TVC99998", full_name="User Test Assignment")
    db.add(person)
    db.commit()
    db.refresh(person)

    asset = Asset(asset_code="GA-LAP-TEST", category_id=cat.id)
    db.add(asset)
    db.commit()
    db.refresh(asset)

    # Assignment 1: 01/01/2026 -> 01/06/2026
    a1 = Assignment(asset_id=asset.id, person_id=person.id, borrowed_at=dt.date(2026, 1, 1), returned_at=dt.date(2026, 6, 1))
    db.add(a1)
    db.commit()

    admin = AssignmentAdmin()
    req = MagicMock()
    req.session = {"lang": "vi"}

    # Thử tạo Assignment 2: 15/05/2026 (trùng lấn với Assignment 1)
    data = {
        "asset": asset,
        "person": person,
        "borrowed_at": dt.date(2026, 5, 15),
    }
    with pytest.raises(ValueError, match="Trùng lặp thời gian cấp phát"):
        asyncio.run(admin.on_model_change(data, Assignment(), is_created=True, request=req))






