"""Kiểm thử tầng nghiệp vụ Nhân sự (Person Service & Profile - FR-05, FR-11) - Giai đoạn 3."""

from __future__ import annotations

import datetime as dt
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.enums import AssetStatus, AuditAction, CardStatus, PersonStatus
from app.models import (
    AccessCard,
    Asset,
    Assignment,
    AuditLog,
    CardLoan,
    Department,
    License,
    LicenseAssignment,
    LicenseProduct,
    Person,
)
from app.services.person_service import (
    create_person,
    get_person_profile,
    soft_delete_person,
    update_person,
)

TODAY = dt.date(2026, 10, 8)


def test_create_person_success(db: Session, seed):
    user_id = seed["user"].id
    dept_id = seed["dept"].id

    data = {
        "staff_code": "TVC-99001",
        "user_login_id": "hung.mai",
        "full_name": "Mai Thanh Hung",
        "email": "hung.mai@tokuyama.vn",
        "department_id": dept_id,
        "status": PersonStatus.ACTIVE,
        "start_working_date": TODAY,
        "note": "Kỹ sư IT mới",
    }
    person = create_person(db, data, user_id=user_id, ip_address="127.0.0.1")
    assert person.id is not None
    assert person.staff_code == "TVC-99001"
    assert person.is_deleted is False

    # Audit log
    audit = db.scalar(
        select(AuditLog).where(
            AuditLog.table_name == "persons",
            AuditLog.record_id == person.id,
            AuditLog.action == AuditAction.CREATE,
        )
    )
    assert audit is not None


def test_create_person_duplicate_staff_code(db: Session, seed):
    user_id = seed["user"].id
    data = {
        "staff_code": seed["person"].staff_code,  # Trùng mã nhân viên
        "full_name": "Người trùng mã",
    }
    with pytest.raises(ValueError, match="đã tồn tại"):
        create_person(db, data, user_id=user_id)


def test_update_person_success(db: Session, seed):
    person = seed["person"]
    user_id = seed["user"].id

    updated = update_person(
        db,
        person.id,
        {"full_name": "Nguyen Van A (Cap nhat)", "note": "Chuyen bo phan"},
        user_id=user_id,
    )
    assert updated.full_name == "Nguyen Van A (Cap nhat)"
    assert updated.note == "Chuyen bo phan"


def test_soft_delete_person_blocked_when_holding_assets(db: Session, seed):
    person = seed["person"]
    asset = seed["asset"]
    user_id = seed["user"].id

    # Đang giữ máy
    db.add(Assignment(asset_id=asset.id, person_id=person.id, borrowed_at=TODAY))
    db.flush()

    with pytest.raises(ValueError, match="đang giữ thiết bị IT"):
        soft_delete_person(db, person.id, delete_reason="Thoi viec", user_id=user_id)


def test_soft_delete_person_blocked_when_holding_card(db: Session, seed):
    person = seed["person_b"]
    card = seed["card"]
    user_id = seed["user"].id

    # Đang mượn thẻ
    db.add(CardLoan(card_id=card.id, person_id=person.id, borrowed_at=TODAY))
    db.flush()

    with pytest.raises(ValueError, match="đang mượn thẻ ra vào"):
        soft_delete_person(db, person.id, delete_reason="Thoi viec", user_id=user_id)


def test_soft_delete_person_blocked_when_holding_license(db: Session, seed):
    person = seed["person_b"]
    lic = seed["license"]
    user_id = seed["user"].id

    # Đang được cấp license
    db.add(LicenseAssignment(license_id=lic.id, person_id=person.id, assigned_at=TODAY))
    db.flush()

    with pytest.raises(ValueError, match="đang được cấp bản quyền"):
        soft_delete_person(db, person.id, delete_reason="Thoi viec", user_id=user_id)


def test_get_person_profile_aggregation(db: Session, seed):
    person = seed["person"]
    asset = seed["asset"]
    lic = seed["license"]
    card = seed["card"]

    # Gán thiết bị, license, thẻ
    db.add(Assignment(asset_id=asset.id, person_id=person.id, borrowed_at=TODAY))
    db.add(LicenseAssignment(license_id=lic.id, person_id=person.id, assigned_at=TODAY))
    db.add(CardLoan(card_id=card.id, person_id=person.id, borrowed_at=TODAY))
    db.flush()

    profile = get_person_profile(db, person.id)
    assert profile is not None
    assert profile["person"].id == person.id
    assert len(profile["active_assets"]) == 1
    assert profile["active_assets"][0].id == asset.id
    assert len(profile["active_licenses"]) == 1
    assert len(profile["active_cards"]) == 1
