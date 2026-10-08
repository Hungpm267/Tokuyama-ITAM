"""Kiểm thử tự động các tính năng hoàn thiện Đợt 1 (FR-17, FR-04, FR-02/BRD 110 & 210).

1. Dashboard Alerts (FR-17): Thẻ mượn quá hạn và License sắp hết hạn <= 60 ngày.
2. Global Search (FR-04): Tìm kiếm đa phân hệ (Asset, Person, Contract, AccessCard, Phone, License).
3. Recycle Bin & Restore (FR-02, BRD 110/210): Danh sách xóa mềm, khôi phục, kiểm tra xung đột partial unique index, audit log RESTORE.
"""

from __future__ import annotations

import datetime as dt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import create_session_token, hash_password
from app.db import get_db
from app.enums import (
    AssetStatus,
    AuditAction,
    CardStatus,
    DEFAULT_ROLE_PERMISSIONS,
    LicenseType,
    PersonStatus,
    RoleCode,
)
from app.main import app
from app.models import (
    AccessCard,
    Asset,
    AssetCategory,
    AuditLog,
    CardLoan,
    Contract,
    License,
    LicenseProduct,
    Person,
    Role,
    RolePermission,
    User,
)


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

    admin = getattr(app.state, "admin", None)
    if admin:
        monkeypatch.setattr(admin, "session_maker", mock_maker)
        for view in admin._views:
            monkeypatch.setattr(view, "session_maker", mock_maker)

    yield
    app.dependency_overrides.clear()


def _get_or_create_admin_user(db: Session) -> User:
    role = db.scalar(select(Role).where(Role.code == RoleCode.ADMIN.value))
    if not role:
        role = Role(code=RoleCode.ADMIN.value, name_en="Administrator")
        db.add(role)
        db.flush()

    for mod, acts in DEFAULT_ROLE_PERMISSIONS.get(RoleCode.ADMIN, {}).items():
        for act in acts:
            existing = db.scalar(
                select(RolePermission).where(
                    RolePermission.role_id == role.id,
                    RolePermission.module == mod.value,
                    RolePermission.action == act.value,
                )
            )
            if not existing:
                db.add(RolePermission(role_id=role.id, module=mod.value, action=act.value))
    db.flush()

    user = db.scalar(select(User).where(User.username == "admin_test_p1"))
    if not user:
        user = User(
            username="admin_test_p1",
            display_name="Admin Test Phase 1",
            password_hash=hash_password("admin_pass_123"),
            role_id=role.id,
            is_active=True,
        )
        db.add(user)
        db.flush()
    return user


def _get_or_create_ga_user(db: Session) -> User:
    role = db.scalar(select(Role).where(Role.code == RoleCode.GA_MANAGER.value))
    if not role:
        role = Role(code=RoleCode.GA_MANAGER.value, name_en="GA Manager")
        db.add(role)
        db.flush()

    for mod, acts in DEFAULT_ROLE_PERMISSIONS.get(RoleCode.GA_MANAGER, {}).items():
        for act in acts:
            existing = db.scalar(
                select(RolePermission).where(
                    RolePermission.role_id == role.id,
                    RolePermission.module == mod.value,
                    RolePermission.action == act.value,
                )
            )
            if not existing:
                db.add(RolePermission(role_id=role.id, module=mod.value, action=act.value))
    db.flush()

    user = db.scalar(select(User).where(User.username == "ga_test_p1"))
    if not user:
        user = User(
            username="ga_test_p1",
            display_name="GA Manager Test",
            password_hash=hash_password("ga_pass_123"),
            role_id=role.id,
            is_active=True,
        )
        db.add(user)
        db.flush()
    return user


def _auth_cookie_token(user: User) -> str:
    return create_session_token({"user_id": user.id, "username": user.username, "role": user.role.code})


# =========================================================================
# 1. DASHBOARD ALERTS TESTS (FR-17)
# =========================================================================

def test_dashboard_alerts_overdue_card_loans(client: TestClient, db: Session):
    """Kiểm tra widget cảnh báo thẻ mượn quá hạn hẹn trả trên Dashboard."""
    admin_user = _get_or_create_admin_user(db)
    client.cookies.set("itam_session", _auth_cookie_token(admin_user))

    today = dt.date.today()
    card = AccessCard(card_no="CARD-ALERT-999", status=CardStatus.IN_STOCK)
    db.add(card)
    db.flush()

    loan = CardLoan(
        card_id=card.id,
        external_name="Contractor Overdue",
        external_company="Overdue Co.",
        borrowed_at=today - dt.timedelta(days=10),
        expected_return_at=today - dt.timedelta(days=3),  # Quá hạn 3 ngày
        returned_at=None,
    )
    db.add(loan)
    db.flush()

    resp = client.get("/admin/", follow_redirects=True)
    assert resp.status_code == 200
    html = resp.text
    assert "CARD-ALERT-999" in html
    assert "Contractor Overdue" in html
    assert "Trễ" in html or "quá hạn" in html


def test_dashboard_alerts_expiring_licenses(client: TestClient, db: Session):
    """Kiểm tra widget cảnh báo bản quyền sắp hết hạn trong vòng 60 ngày."""
    admin_user = _get_or_create_admin_user(db)
    client.cookies.set("itam_session", _auth_cookie_token(admin_user))

    today = dt.date.today()
    prod = LicenseProduct(name="Trend Micro Test Apex", license_type=LicenseType.SUBSCRIPTION)
    db.add(prod)
    db.flush()

    lic = License(
        product_id=prod.id,
        seats=10,
        start_date=today - dt.timedelta(days=300),
        expiry_date=today + dt.timedelta(days=20),  # Hết hạn sau 20 ngày
        note="Sắp hết hạn gói 2026",
    )
    db.add(lic)
    db.flush()

    resp = client.get("/admin/", follow_redirects=True)
    assert resp.status_code == 200
    html = resp.text
    assert "Trend Micro Test Apex" in html
    assert "Sắp hết hạn gói 2026" in html


# =========================================================================
# 2. GLOBAL SEARCH TESTS (FR-04)
# =========================================================================

def test_global_search_finds_asset_by_serial_and_mac(client: TestClient, db: Session):
    """Kiểm tra tìm kiếm toàn cục tìm thấy thiết bị qua Serial, MAC, mã GA."""
    admin_user = _get_or_create_admin_user(db)
    client.cookies.set("itam_session", _auth_cookie_token(admin_user))

    cat = db.scalar(select(AssetCategory).where(AssetCategory.name_en == "Laptop"))
    if not cat:
        cat = AssetCategory(name_en="Laptop")
        db.add(cat)
        db.flush()

    asset = Asset(
        category_id=cat.id,
        asset_code="GA-SRCH-1234",
        serial="SN-SRCH-9999",
        mac_ethernet="AA:BB:CC:11:22:33",
        model="Dell Latitude 5540 SearchTest",
        status=AssetStatus.IN_STOCK,
    )
    db.add(asset)
    db.flush()

    # Tìm theo Serial
    resp_sn = client.get("/admin/global-search?q=SN-SRCH-9999", follow_redirects=True)
    assert resp_sn.status_code == 200
    assert "GA-SRCH-1234" in resp_sn.text
    assert "Dell Latitude 5540 SearchTest" in resp_sn.text

    # Tìm theo MAC
    resp_mac = client.get("/admin/global-search?q=AA:BB:CC:11:22:33", follow_redirects=True)
    assert resp_mac.status_code == 200
    assert "GA-SRCH-1234" in resp_mac.text

    # Tìm theo mã GA
    resp_ga = client.get("/admin/global-search?q=GA-SRCH-1234", follow_redirects=True)
    assert resp_ga.status_code == 200
    assert "Dell Latitude 5540 SearchTest" in resp_ga.text


def test_global_search_finds_person_and_contract(client: TestClient, db: Session):
    """Kiểm tra tìm kiếm toàn cục tìm thấy nhân sự và hợp đồng."""
    admin_user = _get_or_create_admin_user(db)
    client.cookies.set("itam_session", _auth_cookie_token(admin_user))

    # Person
    p = Person(
        staff_code="TVC-SRCH-777",
        full_name="Nguyen Van Tim Kiem",
        user_login_id="timkiem.nguyen",
        email="timkiem@tokuyama.vn",
        status=PersonStatus.ACTIVE,
    )
    db.add(p)

    # Contract
    c = Contract(
        code="KHCM-SRCH-8888",
        vendor_name="KDDI Search Partner",
        signed_date=dt.date(2026, 8, 15),
    )
    db.add(c)
    db.flush()

    # Search Person
    resp_p = client.get("/admin/global-search?q=TVC-SRCH-777", follow_redirects=True)
    assert resp_p.status_code == 200
    assert "Nguyen Van Tim Kiem" in resp_p.text
    assert "timkiem.nguyen" in resp_p.text

    # Search Contract
    resp_c = client.get("/admin/global-search?q=KHCM-SRCH-8888", follow_redirects=True)
    assert resp_c.status_code == 200
    assert "KDDI Search Partner" in resp_c.text


def test_global_search_empty_result(client: TestClient, db: Session):
    """Kiểm tra khi không có kết quả phù hợp."""
    admin_user = _get_or_create_admin_user(db)
    client.cookies.set("itam_session", _auth_cookie_token(admin_user))

    resp = client.get("/admin/global-search?q=NOT_EXISTING_KEYWORD_XYZ_999", follow_redirects=True)
    assert resp.status_code == 200
    assert "Không tìm thấy kết quả" in resp.text or "No matching results" in resp.text


# =========================================================================
# 3. RECYCLE BIN & RESTORE TESTS (FR-02, BRD 110/210)
# =========================================================================

def test_trash_list_shows_soft_deleted_records(client: TestClient, db: Session):
    """Kiểm tra màn hình Thùng rác hiển thị các bản ghi đã xóa mềm."""
    admin_user = _get_or_create_admin_user(db)
    client.cookies.set("itam_session", _auth_cookie_token(admin_user))

    cat = db.scalar(select(AssetCategory).where(AssetCategory.name_en == "Laptop"))
    if not cat:
        cat = AssetCategory(name_en="Laptop")
        db.add(cat)
        db.flush()

    del_asset = Asset(
        category_id=cat.id,
        asset_code="GA-DEL-101",
        serial="SN-DEL-101",
        model="Old ThinkPad T490",
        is_deleted=True,
        deleted_at=dt.datetime.now(dt.timezone.utc),
        deleted_by=admin_user.id,
        delete_reason="Thiết bị hỏng mainboard thanh lý",
    )
    db.add(del_asset)
    db.flush()

    resp = client.get("/admin/trash", follow_redirects=True)
    assert resp.status_code == 200
    assert "GA-DEL-101" in resp.text
    assert "Thiết bị hỏng mainboard thanh lý" in resp.text


def test_trash_restore_success_and_audited(client: TestClient, db: Session):
    """Khôi phục thành công bản ghi xóa mềm và ghi audit log RESTORE."""
    admin_user = _get_or_create_admin_user(db)
    client.cookies.set("itam_session", _auth_cookie_token(admin_user))

    cat = db.scalar(select(AssetCategory).where(AssetCategory.name_en == "Laptop"))
    if not cat:
        cat = AssetCategory(name_en="Laptop")
        db.add(cat)
        db.flush()

    del_asset = Asset(
        category_id=cat.id,
        asset_code="GA-RESTORE-202",
        serial="SN-RESTORE-202",
        model="Latitude 5420 RestoreMe",
        is_deleted=True,
        deleted_at=dt.datetime.now(dt.timezone.utc),
        deleted_by=admin_user.id,
        delete_reason="Xóa nhầm cần khôi phục",
    )
    db.add(del_asset)
    db.flush()

    # Thực hiện gọi restore
    resp = client.post(
        "/admin/trash/restore",
        data={"entity_type": "asset", "item_id": del_asset.id},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True

    # Kiểm tra trạng thái trong DB
    db.refresh(del_asset)
    assert del_asset.is_deleted is False
    assert del_asset.deleted_at is None
    assert del_asset.delete_reason is None

    # Kiểm tra Audit Log có ghi RESTORE
    log = db.scalar(
        select(AuditLog)
        .where(
            AuditLog.table_name == "assets",
            AuditLog.record_id == del_asset.id,
            AuditLog.action == AuditAction.RESTORE,
        )
        .order_by(AuditLog.id.desc())
    )
    assert log is not None
    assert log.user_id == admin_user.id


def test_trash_restore_conflict_prevention(client: TestClient, db: Session):
    """Chặn khôi phục nếu serial đã bị trùng với một bản ghi đang sống."""
    admin_user = _get_or_create_admin_user(db)
    client.cookies.set("itam_session", _auth_cookie_token(admin_user))

    cat = db.scalar(select(AssetCategory).where(AssetCategory.name_en == "Laptop"))
    if not cat:
        cat = AssetCategory(name_en="Laptop")
        db.add(cat)
        db.flush()

    # 1. Bản ghi đang sống
    alive_asset = Asset(
        category_id=cat.id,
        asset_code="GA-ALIVE-301",
        serial="DUPLICATE-SN-301",
        model="New Machine",
        is_deleted=False,
    )
    db.add(alive_asset)

    # 2. Bản ghi đã xóa mềm có cùng serial
    del_asset = Asset(
        category_id=cat.id,
        asset_code="GA-DEL-302",
        serial="DUPLICATE-SN-301",  # Cùng serial
        model="Old Machine",
        is_deleted=True,
        deleted_at=dt.datetime.now(dt.timezone.utc),
        deleted_by=admin_user.id,
        delete_reason="Đã từng xóa",
    )
    db.add(del_asset)
    db.flush()

    # Thử khôi phục bản ghi đã xóa
    resp = client.post(
        "/admin/trash/restore",
        data={"entity_type": "asset", "item_id": del_asset.id},
        follow_redirects=True,
    )
    assert resp.status_code == 400
    assert "hiện đã được sử dụng" in resp.json()["detail"]

    # Xác nhận bản ghi vẫn giữ is_deleted = True
    db.refresh(del_asset)
    assert del_asset.is_deleted is True


def test_trash_access_denied_for_non_admin(client: TestClient, db: Session):
    """GA Manager không có quyền truy cập Thùng rác (BRD dòng 110 & 210)."""
    ga_user = _get_or_create_ga_user(db)
    client.cookies.set("itam_session", _auth_cookie_token(ga_user))

    resp = client.get("/admin/trash", follow_redirects=True)
    assert resp.status_code == 403
    assert "Chỉ Quản trị viên" in resp.json()["detail"]
