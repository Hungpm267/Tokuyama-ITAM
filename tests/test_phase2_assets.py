"""Kiểm thử tầng nghiệp vụ Tài sản (Asset Service) - Giai đoạn 2."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.enums import AssetStatus, AuditAction
from app.models import AssetTag, AuditLog
from app.services.asset_service import (
    create_asset,
    get_asset_tags,
    set_asset_tags,
    soft_delete_asset,
    update_asset,
)


def test_create_asset_success(db: Session, seed):
    user_id = seed["user"].id
    cat_id = seed["cat"].id

    data = {
        "asset_code": "GA-NEW-001",
        "vendor_code": "VEN-NEW-001",
        "serial": "SN-NEW-001",
        "model": "Latitude 5430",
        "form_factor": "Laptop",
        "category_id": cat_id,
        "mac_ethernet": "00:11:22:33:44:55",
        "mac_wifi": "AA:BB:CC:DD:EE:FF",
        "note": "Thiết bị mới nhập kho",
    }

    asset = create_asset(db=db, data=data, user_id=user_id, ip_address="127.0.0.1")
    assert asset.id is not None
    assert asset.asset_code == "GA-NEW-001"
    assert asset.status == AssetStatus.IN_STOCK
    assert asset.is_deleted is False

    # Kiểm tra audit log
    audit = db.scalar(
        select(AuditLog)
        .where(
            AuditLog.table_name == "assets",
            AuditLog.record_id == asset.id,
            AuditLog.action == AuditAction.CREATE,
        )
    )
    assert audit is not None
    assert audit.user_id == user_id
    assert audit.before_after is not None
    assert audit.before_after["after"]["asset_code"] == "GA-NEW-001"


def test_create_asset_requires_identifier(db: Session, seed):
    cat_id = seed["cat"].id
    # Không có cả asset_code, vendor_code lẫn serial
    data = {
        "category_id": cat_id,
        "model": "Unknown model",
    }
    with pytest.raises(ValueError, match="ít nhất một trong các định danh"):
        create_asset(db=db, data=data, user_id=seed["user"].id)


def test_update_asset_success(db: Session, seed):
    asset = seed["asset"]
    user_id = seed["user"].id

    update_data = {
        "model": "Latitude 5430 Updated",
        "note": "Đã cài đặt phần mềm",
    }
    updated = update_asset(db=db, asset_id=asset.id, data=update_data, user_id=user_id)
    assert updated.model == "Latitude 5430 Updated"
    assert updated.note == "Đã cài đặt phần mềm"

    # Audit log UPDATE
    audit = db.scalar(
        select(AuditLog)
        .where(
            AuditLog.table_name == "assets",
            AuditLog.record_id == asset.id,
            AuditLog.action == AuditAction.UPDATE,
        )
        .order_by(AuditLog.id.desc())
    )
    assert audit is not None
    assert audit.before_after["after"]["model"] == "Latitude 5430 Updated"


def test_soft_delete_asset_success(db: Session, seed):
    asset = seed["asset"]
    user_id = seed["user"].id

    deleted = soft_delete_asset(
        db=db,
        asset_id=asset.id,
        delete_reason="Nhập trùng thông tin",
        user_id=user_id,
    )
    assert deleted.is_deleted is True
    assert deleted.delete_reason == "Nhập trùng thông tin"
    assert deleted.deleted_by == user_id
    assert deleted.deleted_at is not None

    # Audit log DELETE
    audit = db.scalar(
        select(AuditLog)
        .where(
            AuditLog.table_name == "assets",
            AuditLog.record_id == asset.id,
            AuditLog.action == AuditAction.DELETE,
        )
    )
    assert audit is not None


def test_soft_delete_asset_requires_reason(db: Session, seed):
    asset = seed["asset"]
    with pytest.raises(ValueError, match="Lý do xóa không được để trống"):
        soft_delete_asset(db=db, asset_id=asset.id, delete_reason="   ")


def test_set_asset_tags(db: Session, seed):
    asset = seed["asset"]
    tag1 = AssetTag(code="ZSCALER", name_en="Zscaler Client Connector")
    tag2 = AssetTag(code="MES", name_en="Manufacturing Execution System")
    db.add_all([tag1, tag2])
    db.flush()

    set_asset_tags(db=db, asset_id=asset.id, tag_ids=[tag1.id, tag2.id], user_id=seed["user"].id)

    tags = get_asset_tags(db, asset.id)
    tag_ids = [t.id for t in tags]
    assert tag1.id in tag_ids
    assert tag2.id in tag_ids
