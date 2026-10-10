"""Kiểm thử tầng nghiệp vụ Bàn giao & Thu hồi thiết bị (Assignment Service) - Giai đoạn 2."""

from __future__ import annotations

import datetime as dt
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.enums import AssetStatus, AuditAction
from app.models import AuditLog
from app.services.assignment_service import (
    assign_asset,
    get_active_assignment,
    get_asset_assignment_history,
    return_asset,
)

TODAY = dt.date(2026, 10, 8)
YESTERDAY = TODAY - dt.timedelta(days=1)
TOMORROW = TODAY + dt.timedelta(days=1)


def test_assign_asset_success(db: Session, seed):
    asset = seed["asset"]
    person = seed["person"]
    user_id = seed["user"].id

    asgn = assign_asset(
        db=db,
        asset_id=asset.id,
        person_id=person.id,
        borrowed_at=YESTERDAY,
        note="Cấp phát máy làm việc",
        user_id=user_id,
        ip_address="127.0.0.1",
    )

    assert asgn.id is not None
    assert asgn.asset_id == asset.id
    assert asgn.person_id == person.id
    assert asgn.borrowed_at == YESTERDAY
    assert asgn.returned_at is None

    # Tự động chuyển trạng thái máy sang IN_USE
    db.refresh(asset)
    assert asset.status == AssetStatus.IN_USE

    # Kiểm tra audit log: CREATE trên assignments, UPDATE trên assets
    asgn_audit = db.scalar(
        select(AuditLog).where(
            AuditLog.table_name == "assignments",
            AuditLog.record_id == asgn.id,
            AuditLog.action == AuditAction.CREATE,
        )
    )
    assert asgn_audit is not None
    assert asgn_audit.user_id == user_id


def test_cannot_assign_asset_already_in_use(db: Session, seed):
    asset = seed["asset"]
    person_a = seed["person"]
    person_b = seed["person_b"]
    user_id = seed["user"].id

    # Lần 1: bàn giao thành công cho person_a
    assign_asset(
        db=db,
        asset_id=asset.id,
        person_id=person_a.id,
        borrowed_at=YESTERDAY,
        user_id=user_id,
    )

    # Lần 2: cố tình bàn giao tiếp cho person_b khi chưa trả
    with pytest.raises(ValueError, match="đang có người sử dụng"):
        assign_asset(
            db=db,
            asset_id=asset.id,
            person_id=person_b.id,
            borrowed_at=TODAY,
            user_id=user_id,
        )


def test_return_asset_success(db: Session, seed):
    asset = seed["asset"]
    person = seed["person"]
    user_id = seed["user"].id

    # 1. Bàn giao
    assign_asset(
        db=db,
        asset_id=asset.id,
        person_id=person.id,
        borrowed_at=YESTERDAY,
        user_id=user_id,
    )

    # 2. Thu hồi về kho IN_STOCK
    returned_asgn = return_asset(
        db=db,
        asset_id=asset.id,
        returned_at=TODAY,
        return_status=AssetStatus.IN_STOCK,
        note="Thu hồi nhân viên chuyển phòng ban",
        user_id=user_id,
    )

    assert returned_asgn.returned_at == TODAY
    db.refresh(asset)
    assert asset.status == AssetStatus.IN_STOCK

    # Kiểm tra active assignment hiện tại là None
    active = get_active_assignment(db, asset.id)
    assert active is None


def test_return_asset_with_repair_status(db: Session, seed):
    asset = seed["asset"]
    person = seed["person"]
    user_id = seed["user"].id

    assign_asset(
        db=db,
        asset_id=asset.id,
        person_id=person.id,
        borrowed_at=YESTERDAY,
        user_id=user_id,
    )

    # Thu hồi báo máy hỏng cần sửa chữa
    return_asset(
        db=db,
        asset_id=asset.id,
        returned_at=TODAY,
        return_status=AssetStatus.REPAIR,
        note="Bàn phím bị liệt phím cách",
        user_id=user_id,
    )

    db.refresh(asset)
    assert asset.status == AssetStatus.REPAIR


def test_return_asset_date_validation(db: Session, seed):
    asset = seed["asset"]
    person = seed["person"]
    user_id = seed["user"].id

    assign_asset(
        db=db,
        asset_id=asset.id,
        person_id=person.id,
        borrowed_at=TODAY,
        user_id=user_id,
    )

    # Cố tình trả trước ngày mượn
    with pytest.raises(ValueError, match="không được trước ngày bàn giao"):
        return_asset(
            db=db,
            asset_id=asset.id,
            returned_at=YESTERDAY,
            user_id=user_id,
        )


def test_assignment_history(db: Session, seed):
    asset = seed["asset"]
    person_a = seed["person"]
    person_b = seed["person_b"]
    user_id = seed["user"].id

    # Người A mượn và trả
    assign_asset(db, asset.id, person_a.id, YESTERDAY, user_id=user_id)
    return_asset(db, asset.id, TODAY, user_id=user_id)

    # Người B mượn
    assign_asset(db, asset.id, person_b.id, TODAY, user_id=user_id)

    history = get_asset_assignment_history(db, asset.id)
    assert len(history) == 2
    assert history[0].person_id == person_b.id  # Sắp xếp mới nhất lên đầu
    assert history[1].person_id == person_a.id


def test_cannot_assign_asset_in_future(db: Session, seed):
    asset = seed["asset"]
    person = seed["person"]
    future_date = dt.date.today() + dt.timedelta(days=7)

    with pytest.raises(ValueError, match="Không được chọn ngày trong tương lai"):
        assign_asset(
            db=db,
            asset_id=asset.id,
            person_id=person.id,
            borrowed_at=future_date,
            user_id=seed["user"].id,
        )


def test_cannot_return_asset_in_future(db: Session, seed):
    asset = seed["asset"]
    person = seed["person"]
    user_id = seed["user"].id

    assign_asset(
        db=db,
        asset_id=asset.id,
        person_id=person.id,
        borrowed_at=dt.date.today() - dt.timedelta(days=1),
        user_id=user_id,
    )

    future_date = dt.date.today() + dt.timedelta(days=3)
    with pytest.raises(ValueError, match="Không được chọn ngày trong tương lai"):
        return_asset(
            db=db,
            asset_id=asset.id,
            returned_at=future_date,
            user_id=user_id,
        )
