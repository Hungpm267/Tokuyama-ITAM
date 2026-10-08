"""Kiểm thử API và quy trình nghiệp vụ Quản lý Mật khẩu Nhân sự (FR-06)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import create_session_token, hash_password
from app.db import get_db
from app.enums import AuditAction, PersonStatus, RoleCode
from app.main import app
from app.models import AuditLog, Person, PersonSecret, Role, User


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
    from app.enums import DEFAULT_ROLE_PERMISSIONS
    from app.models import RolePermission

    role = db.scalar(select(Role).where(Role.code == code))
    if not role:
        role = Role(code=code, name_en=name_en)
        db.add(role)
        db.flush()
        role_enum = None
        for r in RoleCode:
            if r.value == code:
                role_enum = r
                break
        if role_enum and role_enum in DEFAULT_ROLE_PERMISSIONS:
            for mod, actions in DEFAULT_ROLE_PERMISSIONS[role_enum].items():
                for act in actions:
                    db.add(RolePermission(
                        role_id=role.id,
                        module=mod.value,
                        action=act.value,
                    ))
        db.commit()
    return role


@pytest.fixture
def admin_user(db: Session) -> User:
    role = _ensure_role(db, RoleCode.ADMIN.value, "Administrator")
    user = db.scalar(select(User).where(User.username == "admin_sec_test"))
    if not user:
        user = User(
            username="admin_sec_test",
            password_hash=hash_password("AdminPass#2026"),
            display_name="Admin Sec Tester",
            role_id=role.id,
            preferred_lang="vi",
            is_active=True,
        )
        db.add(user)
        db.commit()
    return user


@pytest.fixture
def ga_user(db: Session) -> User:
    role = _ensure_role(db, RoleCode.GA_MANAGER.value, "General Affairs")
    user = db.scalar(select(User).where(User.username == "ga_sec_test"))
    if not user:
        user = User(
            username="ga_sec_test",
            password_hash=hash_password("GaPass#2026"),
            display_name="GA Sec Tester",
            role_id=role.id,
            preferred_lang="vi",
            is_active=True,
        )
        db.add(user)
        db.commit()
    return user


@pytest.fixture
def test_person(db: Session) -> Person:
    person = db.scalar(select(Person).where(Person.staff_code == "TEST_STAFF_001"))
    if not person:
        person = Person(
            staff_code="TEST_STAFF_001",
            full_name="Nguyễn Văn Test",
            status=PersonStatus.ACTIVE,
            email="test_staff@tokuyama.vn",
        )
        db.add(person)
        db.commit()
    return person


def test_non_admin_cannot_save_or_reveal_secret(
    client: TestClient, ga_user: User, test_person: Person
):
    token = create_session_token(
        {"user_id": ga_user.id, "username": ga_user.username, "role": RoleCode.GA_MANAGER.value}
    )
    client.cookies.set("itam_session", token)

    # 1. Thử lưu mật khẩu -> 403 Forbidden
    resp = client.post(
        "/admin/person-secret/save",
        json={"person_id": test_person.id, "pc_password": "NewPassword123"},
    )
    assert resp.status_code == 403

    # 2. Thử xem mật khẩu -> 403 Forbidden
    resp = client.post(
        f"/persons/{test_person.id}/secrets/reveal",
        json={"field": "pc_password", "admin_password": "GaPass#2026"},
    )
    assert resp.status_code == 403


def test_admin_can_save_and_reveal_secret(
    client: TestClient, admin_user: User, test_person: Person, db: Session
):
    token = create_session_token(
        {"user_id": admin_user.id, "username": admin_user.username, "role": RoleCode.ADMIN.value}
    )
    client.cookies.set("itam_session", token)

    # 1. Lưu mật khẩu PC và Email
    save_resp = client.post(
        "/admin/person-secret/save",
        json={
            "person_id": test_person.id,
            "pc_password": "PCSecretTokuyama#99",
            "pc_password_note": "Máy bàn kế toán",
            "email_password": "EmailSecretTokuyama#88",
            "email_password_note": "Hộp thư Outlook",
        },
    )
    assert save_resp.status_code == 200
    save_data = save_resp.json()
    assert save_data["success"] is True

    # 2. Kiểm tra trong DB: bản ghi person_secrets đã được mã hoá AES-256-GCM, không chứa chuỗi rõ
    db.expire_all()
    secret = db.scalar(select(PersonSecret).where(PersonSecret.person_id == test_person.id))
    assert secret is not None
    assert secret.pc_password_enc is not None
    assert b"PCSecretTokuyama" not in secret.pc_password_enc
    assert secret.pc_password_note == "Máy bàn kế toán"
    assert secret.email_password_enc is not None
    assert b"EmailSecretTokuyama" not in secret.email_password_enc

    # 3. Thử xem với mật khẩu Admin sai -> 401 Unauthorized
    bad_resp = client.post(
        f"/persons/{test_person.id}/secrets/reveal",
        json={"field": "pc_password", "admin_password": "WrongAdminPassword"},
    )
    assert bad_resp.status_code == 401
    assert bad_resp.json()["success"] is False

    # 4. Xem với mật khẩu Admin đúng -> thành công, trả về reveal_token và plaintext
    reveal_resp = client.post(
        f"/persons/{test_person.id}/secrets/reveal",
        json={"field": "pc_password", "admin_password": "AdminPass#2026"},
    )
    assert reveal_resp.status_code == 200
    reveal_data = reveal_resp.json()
    assert reveal_data["success"] is True
    assert reveal_data["value"] == "PCSecretTokuyama#99"
    assert "reveal_token" in reveal_data
    reveal_token = reveal_data["reveal_token"]

    # 5. Dùng reveal_token để xem tiếp mật khẩu Email mà không cần nhập lại mật khẩu Admin
    reveal_email_resp = client.post(
        f"/persons/{test_person.id}/secrets/reveal",
        json={"field": "email_password", "reveal_token": reveal_token},
    )
    assert reveal_email_resp.status_code == 200
    email_data = reveal_email_resp.json()
    assert email_data["success"] is True
    assert email_data["value"] == "EmailSecretTokuyama#88"

    # 6. Kiểm tra Audit Log: phải ghi nhận action = REVEAL
    db.expire_all()
    reveal_audits = db.scalars(
        select(AuditLog).where(
            AuditLog.table_name == "person_secrets",
            AuditLog.record_id == test_person.id,
            AuditLog.action == AuditAction.REVEAL,
        )
    ).all()
    assert len(reveal_audits) >= 2
    for audit in reveal_audits:
        # Đảm bảo không chứa mật khẩu trong audit log
        raw_str = str(audit.before_after)
        assert "PCSecretTokuyama" not in raw_str
        assert "EmailSecretTokuyama" not in raw_str


def test_admin_can_clear_secret(
    client: TestClient, admin_user: User, test_person: Person, db: Session
):
    token = create_session_token(
        {"user_id": admin_user.id, "username": admin_user.username, "role": RoleCode.ADMIN.value}
    )
    client.cookies.set("itam_session", token)

    # Xoá mật khẩu PC
    resp = client.post(
        "/admin/person-secret/save",
        json={
            "person_id": test_person.id,
            "clear_pc_password": True,
        },
    )
    assert resp.status_code == 200
    db.expire_all()
    secret = db.scalar(select(PersonSecret).where(PersonSecret.person_id == test_person.id))
    assert secret.pc_password_enc is None
    assert secret.pc_password_note is None
