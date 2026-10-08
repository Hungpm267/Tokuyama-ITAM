"""Kiểm thử tầng nghiệp vụ và endpoint Phase 5 (FR-15 Danh bạ thoại, FR-18 Xuất CSV)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db import get_db
from app.enums import Module, PermissionAction, PhoneDeviceType
from app.main import app
from app.models import REDACTED_FIELDS, RolePermission
from app.services.phone_service import (
    create_phone,
    delete_phone,
    list_phones,
    update_phone,
)


# =============================================================================
# 1. Phone Service Tests (FR-15)
# =============================================================================

def test_create_and_list_phones(db: Session, seed):
    loc = seed["location"]
    user_id = seed["user"].id

    phone1 = create_phone(
        db=db,
        device_name="TEL-OFFICE-01",
        device_type=PhoneDeviceType.IP_PHONE,
        extension_number="101",
        location_id=loc.id,
        remarks="Bàn GA",
        user_id=user_id,
    )
    assert phone1.id is not None
    assert phone1.extension_number == "101"

    phones = list_phones(db)
    assert any(p.device_name == "TEL-OFFICE-01" for p in phones)


def test_create_phone_rejects_duplicate_device_or_ext(db: Session, seed):
    create_phone(
        db=db,
        device_name="TEL-OFFICE-DUP",
        device_type=PhoneDeviceType.IP_PHONE,
        extension_number="102",
    )

    with pytest.raises(ValueError, match="đã tồn tại"):
        create_phone(
            db=db,
            device_name="TEL-OFFICE-DUP",
            device_type=PhoneDeviceType.IP_PHONE,
            extension_number="103",
        )

    with pytest.raises(ValueError, match="đã được sử dụng"):
        create_phone(
            db=db,
            device_name="TEL-OFFICE-OTHER",
            device_type=PhoneDeviceType.IP_PHONE,
            extension_number="102",
        )


def test_create_phone_handles_na_extension(db: Session):
    phone = create_phone(
        db=db,
        device_name="WT-SECURITY-01",
        device_type=PhoneDeviceType.WIFI_PHONE,
        extension_number="N/A",  # Quy ước DB: N/A chuyển thành None
    )
    assert phone.extension_number is None


def test_update_and_soft_delete_phone(db: Session, seed):
    phone = create_phone(
        db=db,
        device_name="TEL-EDIT-01",
        device_type=PhoneDeviceType.IP_PHONE,
        extension_number="105",
    )

    updated = update_phone(
        db=db,
        phone_id=phone.id,
        extension_number="106",
        remarks="Đổi số nhánh",
    )
    assert updated.extension_number == "106"
    assert updated.remarks == "Đổi số nhánh"

    # Soft delete bắt buộc có lý do
    with pytest.raises(ValueError, match="Bắt buộc phải có lý do"):
        delete_phone(db, phone.id, delete_reason="")

    deleted = delete_phone(db, phone.id, delete_reason="Hỏng phần cứng đã thanh lý")
    assert deleted.is_deleted is True
    assert deleted.is_active is False
    assert deleted.delete_reason == "Hỏng phần cứng đã thanh lý"

    active_phones = list_phones(db)
    assert not any(p.id == phone.id for p in active_phones)


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


def test_export_assets_csv(auth_client: TestClient, db: Session, seed):
    res = auth_client.get("/admin/export/assets")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/csv")
    content = res.text
    # Kiểm tra UTF-8 BOM
    assert content.startswith("\ufeff")
    # Kiểm tra có serial tài sản
    assert seed["asset"].serial in content
    # TUYỆT ĐỐI KHÔNG lộ redacted fields
    for field in REDACTED_FIELDS:
        assert field not in content


def test_export_licenses_csv(auth_client: TestClient, db: Session, seed):
    res = auth_client.get("/admin/export/licenses")
    assert res.status_code == 200
    content = res.text
    assert "Trend Micro" in content
    assert "13" in content
    for field in REDACTED_FIELDS:
        assert field not in content


def test_export_cards_csv(auth_client: TestClient, db: Session, seed):
    res = auth_client.get("/admin/export/cards")
    assert res.status_code == 200
    content = res.text
    assert seed["card"].card_no in content


def test_export_persons_csv_never_leaks_passwords(auth_client: TestClient, db: Session, seed):
    res = auth_client.get("/admin/export/persons")
    assert res.status_code == 200
    content = res.text
    assert seed["person"].staff_code in content
    assert seed["person"].full_name in content

    # Bất biến GEMINI.md: Không có cột mật khẩu nào lọt vào CSV
    for forbidden in ["password", "pc_password_enc", "email_password_enc", "password_hash"]:
        assert forbidden not in content


def test_export_phones_csv(auth_client: TestClient, db: Session, seed):
    create_phone(db, "TEL-EXPORT-01", PhoneDeviceType.IP_PHONE, extension_number="333")
    res = auth_client.get("/admin/export/phones")
    assert res.status_code == 200
    content = res.text
    assert "TEL-EXPORT-01" in content
    assert "333" in content


def test_export_endpoint_requires_authentication(db: Session):
    client = TestClient(app)
    # Không có cookie phiên
    res = client.get("/admin/export/assets")
    assert res.status_code == 401


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

