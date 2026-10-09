"""Dịch vụ nghiệp vụ quản lý Tài sản IT (Asset Service - FR-07, FR-08, FR-09)."""

from __future__ import annotations

import datetime as dt
from typing import Any
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.audit import record_audit
from app.enums import AssetStatus, AuditAction
from app.models import Asset, AssetCategory, AssetTag, AssetTagLink, Assignment, ContractLine
from app.services.contract_service import sync_contract_delivery_status


def _asset_to_dict(asset: Asset) -> dict[str, Any]:
    """Chuyển đổi thực thể Asset thành dict để ghi audit log."""
    return {
        "id": asset.id,
        "asset_code": asset.asset_code,
        "vendor_code": asset.vendor_code,
        "category_id": asset.category_id,
        "contract_line_id": asset.contract_line_id,
        "model": asset.model,
        "form_factor": asset.form_factor,
        "serial": asset.serial,
        "hwid": asset.hwid,
        "mac_ethernet": asset.mac_ethernet,
        "mac_wifi": asset.mac_wifi,
        "status": asset.status.value if isinstance(asset.status, AssetStatus) else str(asset.status),
        "note": asset.note,
        "is_deleted": asset.is_deleted,
    }


def get_asset(db: Session, asset_id: int) -> Asset | None:
    """Lấy thông tin tài sản kèm theo quan hệ."""
    return db.scalar(
        select(Asset)
        .options(
            selectinload(Asset.category),
            selectinload(Asset.contract_line),
            selectinload(Asset.assignments).selectinload(Assignment.person),
        )
        .where(Asset.id == asset_id, Asset.is_deleted.is_(False))
    )


def get_asset_tags(db: Session, asset_id: int) -> list[AssetTag]:
    """Lấy danh sách các nhãn gán cho tài sản."""
    return db.scalars(
        select(AssetTag)
        .join(AssetTagLink, AssetTag.id == AssetTagLink.tag_id)
        .where(AssetTagLink.asset_id == asset_id, AssetTag.is_deleted.is_(False))
    ).all()


def create_asset(
    db: Session,
    data: dict[str, Any],
    user_id: int | None = None,
    ip_address: str | None = None,
) -> Asset:
    """Tạo mới tài sản IT và ghi audit log CREATE."""
    asset_code = (data.get("asset_code") or "").strip() or None
    vendor_code = (data.get("vendor_code") or "").strip() or None
    serial = (data.get("serial") or "").strip() or None

    # Kiểm tra ràng buộc DB: ít nhất 1 định danh không được rỗng
    if not (asset_code or vendor_code or serial):
        raise ValueError("Thiết bị phải có ít nhất một trong các định danh: Mã GA, Mã Vendor hoặc Serial.")

    category_id = data.get("category_id")
    if not category_id:
        raise ValueError("Vui lòng chọn Loại tài sản (Category).")

    cat = db.scalar(select(AssetCategory).where(AssetCategory.id == int(category_id), AssetCategory.is_deleted.is_(False)))
    if not cat:
        raise ValueError(f"Loại tài sản với ID {category_id} không tồn tại hoặc đã bị xóa.")

    # Kiểm tra trùng lặp trên các bản ghi chưa bị xóa
    if serial:
        dup = db.scalar(select(Asset).where(Asset.serial == serial, Asset.is_deleted.is_(False)))
        if dup:
            raise ValueError(f"Số serial '{serial}' đã tồn tại trong hệ thống.")
    if asset_code:
        dup = db.scalar(select(Asset).where(Asset.asset_code == asset_code, Asset.is_deleted.is_(False)))
        if dup:
            raise ValueError(f"Mã GA '{asset_code}' đã tồn tại trong hệ thống.")
    if vendor_code:
        dup = db.scalar(select(Asset).where(Asset.vendor_code == vendor_code, Asset.is_deleted.is_(False)))
        if dup:
            raise ValueError(f"Mã Vendor '{vendor_code}' đã tồn tại trong hệ thống.")

    status_val = data.get("status") or AssetStatus.IN_STOCK
    if isinstance(status_val, str):
        status_val = AssetStatus(status_val)

    asset = Asset(
        asset_code=asset_code,
        vendor_code=vendor_code,
        category_id=int(category_id),
        contract_line_id=data.get("contract_line_id"),
        model=(data.get("model") or "").strip() or None,
        form_factor=(data.get("form_factor") or "").strip() or None,
        serial=serial,
        hwid=(data.get("hwid") or "").strip() or None,
        mac_ethernet=(data.get("mac_ethernet") or "").strip() or None,
        mac_wifi=(data.get("mac_wifi") or "").strip() or None,
        status=status_val,
        note=(data.get("note") or "").strip() or None,
        created_by=user_id,
        updated_by=user_id,
    )
    db.add(asset)
    db.flush()

    # Xử lý tags nếu có
    tag_ids = data.get("tag_ids")
    if tag_ids and isinstance(tag_ids, list):
        for t_id in tag_ids:
            db.add(AssetTagLink(asset_id=asset.id, tag_id=int(t_id)))
        db.flush()

    # Ghi audit log
    record_audit(
        db=db,
        action=AuditAction.CREATE,
        table_name="assets",
        record_id=asset.id,
        user_id=user_id,
        after=_asset_to_dict(asset),
        ip_address=ip_address,
    )
    db.flush()
    return asset


def update_asset(
    db: Session,
    asset_id: int,
    data: dict[str, Any],
    user_id: int | None = None,
    ip_address: str | None = None,
) -> Asset:
    """Cập nhật thông tin tài sản và ghi audit log UPDATE."""
    asset = db.scalar(select(Asset).where(Asset.id == asset_id, Asset.is_deleted.is_(False)))
    if not asset:
        raise ValueError(f"Không tìm thấy tài sản có ID {asset_id}.")

    before_dict = _asset_to_dict(asset)

    # Cập nhật các trường được phép
    updatable_fields = [
        "asset_code", "vendor_code", "category_id", "contract_line_id",
        "model", "form_factor", "serial", "hwid", "mac_ethernet",
        "mac_wifi", "status", "note",
    ]

    for field in updatable_fields:
        if field in data:
            val = data[field]
            if isinstance(val, str):
                val = val.strip() or None
            if field == "status" and val is not None and not isinstance(val, AssetStatus):
                val = AssetStatus(val)
            setattr(asset, field, val)

    # Ràng buộc DB
    if not (asset.asset_code or asset.vendor_code or asset.serial):
        raise ValueError("Thiết bị phải có ít nhất một trong các định danh: Mã GA, Mã Vendor hoặc Serial.")

    asset.updated_by = user_id
    asset.updated_at = dt.datetime.now(dt.timezone.utc)
    db.flush()

    # Cập nhật tags nếu có trong payload
    if "tag_ids" in data:
        tag_ids = data["tag_ids"] or []
        set_asset_tags(db, asset.id, tag_ids, user_id=user_id, ip_address=ip_address)

    after_dict = _asset_to_dict(asset)

    record_audit(
        db=db,
        action=AuditAction.UPDATE,
        table_name="assets",
        record_id=asset.id,
        user_id=user_id,
        before=before_dict,
        after=after_dict,
        ip_address=ip_address,
    )
    db.flush()
    return asset


def soft_delete_asset(
    db: Session,
    asset_id: int,
    delete_reason: str,
    user_id: int | None = None,
    ip_address: str | None = None,
) -> Asset:
    """Xóa mềm tài sản với lý do bắt buộc và ghi audit log DELETE."""
    clean_reason = (delete_reason or "").strip()
    if not clean_reason:
        raise ValueError("Lý do xóa không được để trống (bắt buộc nhập theo GEMINI.md).")

    asset = db.scalar(select(Asset).where(Asset.id == asset_id, Asset.is_deleted.is_(False)))
    if not asset:
        raise ValueError(f"Không tìm thấy tài sản có ID {asset_id}.")

    # Kiểm tra xem máy có đang được cho mượn không
    active_assignment = db.scalar(
        select(Assignment).where(
            Assignment.asset_id == asset_id,
            Assignment.returned_at.is_(None),
            Assignment.is_deleted.is_(False),
        )
    )
    if active_assignment or asset.status == AssetStatus.IN_USE:
        raise ValueError("Không thể xóa tài sản đang có người sử dụng. Hãy thu hồi thiết bị trước khi xóa.")

    before_dict = _asset_to_dict(asset)

    asset.is_deleted = True
    asset.delete_reason = clean_reason
    asset.deleted_by = user_id
    asset.deleted_at = dt.datetime.now(dt.timezone.utc)
    db.flush()

    if asset.contract_line_id:
        line = db.get(ContractLine, asset.contract_line_id)
        if line:
            sync_contract_delivery_status(db, line.contract_id)

    after_dict = _asset_to_dict(asset)

    record_audit(
        db=db,
        action=AuditAction.DELETE,
        table_name="assets",
        record_id=asset.id,
        user_id=user_id,
        before=before_dict,
        after=after_dict,
        ip_address=ip_address,
    )
    db.flush()
    return asset


def set_asset_tags(
    db: Session,
    asset_id: int,
    tag_ids: list[int],
    user_id: int | None = None,
    ip_address: str | None = None,
) -> None:
    """Cập nhật danh sách nhãn (tags) của tài sản."""
    asset = db.scalar(select(Asset).where(Asset.id == asset_id, Asset.is_deleted.is_(False)))
    if not asset:
        raise ValueError(f"Không tìm thấy tài sản có ID {asset_id}.")

    # Xóa các liên kết nhãn cũ
    existing_links = db.scalars(select(AssetTagLink).where(AssetTagLink.asset_id == asset_id)).all()
    for link in existing_links:
        db.delete(link)
    db.flush()

    # Thêm các liên kết nhãn mới
    for t_id in set(tag_ids):
        tag = db.scalar(select(AssetTag).where(AssetTag.id == int(t_id), AssetTag.is_deleted.is_(False)))
        if tag:
            db.add(AssetTagLink(asset_id=asset_id, tag_id=tag.id))
    db.flush()
