"""Dịch vụ nghiệp vụ Quản lý Bản quyền / License (Phase 4 - FR-12)."""

from __future__ import annotations

import datetime as dt
from typing import Any
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.audit import record_audit
from app.core.clock import today_local
from app.enums import AssetStatus, AuditAction, ContractItemKind, PersonStatus
from app.models import (
    Asset,
    Contract,
    ContractLine,
    License,
    LicenseAssignment,
    LicenseProduct,
    Person,
)
from app.services.contract_service import line_received_qty, sync_contract_delivery_status


def get_license_seats_summary(db: Session, license_id: int) -> dict[str, Any]:
    """Thống kê số lượng seat đã cấp và còn lại của một License."""
    lic = db.get(License, license_id)
    if not lic or lic.is_deleted:
        raise ValueError(f"License ID {license_id} không tồn tại hoặc đã bị xoá")

    active_count = (
        db.scalar(
            select(func.count(LicenseAssignment.id)).where(
                LicenseAssignment.license_id == license_id,
                LicenseAssignment.removed_at.is_(None),
                LicenseAssignment.is_deleted.is_(False),
            )
        )
        or 0
    )

    return {
        "license": lic,
        "total_seats": lic.seats,
        "assigned_seats": active_count,
        "remaining_seats": max(0, lic.seats - active_count),
    }


def assign_license(
    db: Session,
    license_id: int,
    person_id: int | None = None,
    asset_id: int | None = None,
    assigned_at: dt.date | None = None,
    expiry_date: dt.date | None = None,
    note: str | None = None,
    user_id: int | None = None,
) -> LicenseAssignment:
    """Gán license cho MỘT máy hoặc MỘT nhân viên.
    
    Quy tắc:
    - Bắt buộc phải có person_id hoặc asset_id.
    - Không thể gán cùng license cho cùng máy hoặc cùng người nếu lần gán trước chưa thu hồi.
    - Kiểm tra số seat còn lại.
    - Ghi audit log CREATE.
    """
    if not person_id and not asset_id:
        raise ValueError("License phải được gán cho máy tính hoặc nhân viên")

    lic = db.scalar(
        select(License)
        .where(License.id == license_id, License.is_deleted.is_(False))
        .with_for_update(of=License)
    )
    if not lic:
        raise ValueError(f"License ID {license_id} không tồn tại hoặc đã bị xoá")

    # Kiểm tra trùng lặp trên thiết bị
    if asset_id:
        asset = db.get(Asset, asset_id)
        if not asset or asset.is_deleted:
            raise ValueError(f"Thiết bị #{asset_id} không tồn tại hoặc đã bị xoá")
        if asset.status in (AssetStatus.DISPOSED, AssetStatus.LOST):
            raise ValueError(
                f"Không thể gán bản quyền cho thiết bị ở trạng thái '{asset.status.value}' (đã thanh lý / mất)."
            )
        existing_asset = db.scalar(
            select(LicenseAssignment).where(
                LicenseAssignment.license_id == license_id,
                LicenseAssignment.asset_id == asset_id,
                LicenseAssignment.removed_at.is_(None),
                LicenseAssignment.is_deleted.is_(False),
            )
        )
        if existing_asset:
            raise ValueError(f"Thiết bị #{asset_id} đã được gán bản quyền này")

    # Kiểm tra trùng lặp trên nhân sự
    if person_id:
        person = db.get(Person, person_id)
        if not person or person.is_deleted:
            raise ValueError(f"Nhân viên #{person_id} không tồn tại hoặc đã bị xoá")
        if person.status == PersonStatus.RESIGNED:
            raise ValueError(f"Không thể gán bản quyền cho nhân viên đã nghỉ việc ({person.full_name})")
        existing_person = db.scalar(
            select(LicenseAssignment).where(
                LicenseAssignment.license_id == license_id,
                LicenseAssignment.person_id == person_id,
                LicenseAssignment.removed_at.is_(None),
                LicenseAssignment.is_deleted.is_(False),
            )
        )
        if existing_person:
            raise ValueError(f"Nhân viên #{person_id} đã được gán bản quyền này")

    # Kiểm tra seat còn lại
    summary = get_license_seats_summary(db, license_id)
    if summary["remaining_seats"] <= 0:
        raise ValueError(
            f"License '{lic}' đã hết lượt gán (tổng {summary['total_seats']} seats)"
        )

    today = today_local()
    eff_assigned_at = assigned_at or today
    if eff_assigned_at > today:
        raise ValueError(
            f"Ngày gán bản quyền ({eff_assigned_at.strftime('%d/%m/%Y')}) không được ở tương lai "
            f"(hôm nay là {today.strftime('%d/%m/%Y')})."
        )
    assignment = LicenseAssignment(
        license_id=license_id,
        asset_id=asset_id,
        person_id=person_id,
        assigned_at=eff_assigned_at,
        expiry_date=expiry_date,
        note=note,
    )
    db.add(assignment)
    db.flush()

    record_audit(
        db=db,
        action=AuditAction.CREATE,
        table_name="license_assignments",
        record_id=assignment.id,
        user_id=user_id,
        after={
            "license_id": license_id,
            "asset_id": asset_id,
            "person_id": person_id,
            "assigned_at": eff_assigned_at,
        },
    )

    return assignment


def revoke_license(
    db: Session,
    assignment_id: int,
    removed_at: dt.date | None = None,
    note: str | None = None,
    user_id: int | None = None,
) -> LicenseAssignment:
    """Thu hồi bản quyền đã cấp (bất biến Rule 7: không xoá, chỉ đóng bằng removed_at)."""
    asgn = db.get(LicenseAssignment, assignment_id)
    if not asgn or asgn.is_deleted:
        raise ValueError(f"Bản ghi gán license #{assignment_id} không tồn tại hoặc đã bị xoá")

    if asgn.removed_at is not None:
        raise ValueError(f"Bản quyền này đã được thu hồi vào ngày {asgn.removed_at}")

    today = today_local()
    eff_removed_at = removed_at or today
    # Ngày thu hồi ở tương lai giải phóng seat ngay hôm nay -> gán vượt số lượng.
    if eff_removed_at > today:
        raise ValueError(
            f"Ngày thu hồi bản quyền ({eff_removed_at.strftime('%d/%m/%Y')}) không được ở tương lai "
            f"(hôm nay là {today.strftime('%d/%m/%Y')})."
        )
    if eff_removed_at < asgn.assigned_at:
        raise ValueError("Ngày thu hồi không được trước ngày gán bản quyền")

    before_state = {
        "removed_at": asgn.removed_at,
        "note": asgn.note,
    }

    asgn.removed_at = eff_removed_at
    if note:
        asgn.note = f"{asgn.note or ''}\n[Thu hồi: {note}]".strip()

    db.flush()

    record_audit(
        db=db,
        action=AuditAction.UPDATE,
        table_name="license_assignments",
        record_id=asgn.id,
        user_id=user_id,
        before=before_state,
        after={
            "removed_at": eff_removed_at,
            "note": asgn.note,
        },
    )

    return asgn


def receive_license_for_line(
    db: Session,
    line_id: int,
    product_id: int,
    seats: int,
    start_date: dt.date | None = None,
    expiry_date: dt.date | None = None,
    note: str | None = None,
    user_id: int | None = None,
    ip_address: str | None = None,
) -> License:
    """Nhận phần mềm cho một hạng mục hợp đồng loại SOFTWARE.

    Tạo một gói license gắn vào hạng mục. Số lượng của hạng mục phần mềm là số
    seat, nên tổng seat đã nhận không được vượt qty_ordered (cùng quy tắc "không
    nhận vượt" của phần cứng).
    """
    # Khoá dòng hạng mục: hai lần nhận đồng thời không cùng lọt qua bước kiểm tra sức chứa.
    line = db.scalar(
        select(ContractLine)
        .where(ContractLine.id == line_id, ContractLine.is_deleted.is_(False))
        .with_for_update(of=ContractLine)
    )
    if not line:
        raise ValueError("Hạng mục hợp đồng không tồn tại hoặc đã bị xóa.")
    contract = db.get(Contract, line.contract_id)
    if not contract or contract.is_deleted:
        raise ValueError("Hợp đồng của hạng mục này không tồn tại hoặc đã bị xóa.")
    if line.item_kind != ContractItemKind.SOFTWARE:
        raise ValueError("Hạng mục này là phần cứng, không thể nhận bằng gói phần mềm.")

    product = db.get(LicenseProduct, product_id)
    if not product or product.is_deleted:
        raise ValueError("Sản phẩm phần mềm không tồn tại hoặc đã bị xóa.")

    if seats is None or seats <= 0:
        raise ValueError("Số lượng bản quyền (seats) phải lớn hơn 0.")
    if start_date and expiry_date and expiry_date < start_date:
        raise ValueError("Ngày hết hạn không được trước ngày kích hoạt.")

    received = line_received_qty(db, line)
    remaining = line.qty_ordered - received
    if seats > remaining:
        raise ValueError(
            f"Hạng mục '{line.item_type}' đặt mua {line.qty_ordered}, đã nhận {received}. "
            f"Chỉ còn nhận được tối đa {max(0, remaining)}, không thể nhận {seats}."
        )

    clean_note = (note or "").strip() or None

    # Nhận nhiều đợt cho cùng một sản phẩm, cùng hạn dùng thì đó vẫn là MỘT gói:
    # cộng seat vào gói đang có thay vì sinh thêm dòng trong Kho License. Chỉ tách
    # gói khi hạn dùng khác nhau, vì cảnh báo hết hạn phải tính riêng từng hạn.
    # (IS NOT DISTINCT FROM để hai gói cùng để trống ngày cũng được coi là giống nhau.)
    existing = db.scalar(
        select(License)
        .where(
            License.contract_line_id == line.id,
            License.product_id == product.id,
            License.is_deleted.is_(False),
            License.start_date.is_not_distinct_from(start_date),
            License.expiry_date.is_not_distinct_from(expiry_date),
        )
        .order_by(License.id)
        .limit(1)
    )
    if existing:
        old_seats = existing.seats
        existing.seats = old_seats + seats
        if clean_note:
            existing.note = f"{existing.note} | {clean_note}" if existing.note else clean_note
        existing.updated_by = user_id
        existing.updated_at = dt.datetime.now(dt.timezone.utc)
        db.flush()
        record_audit(
            db=db,
            action=AuditAction.UPDATE,
            table_name="licenses",
            record_id=existing.id,
            user_id=user_id,
            before={"seats": old_seats},
            after={"seats": existing.seats},
            extra={"received_seats": seats, "contract_line_id": line.id},
            ip_address=ip_address,
        )
        sync_contract_delivery_status(db, contract.id)
        db.flush()
        return existing

    lic = License(
        product_id=product.id,
        seats=seats,
        start_date=start_date,
        expiry_date=expiry_date,
        contract_id=contract.id,
        contract_line_id=line.id,
        note=clean_note,
        created_by=user_id,
        updated_by=user_id,
    )
    db.add(lic)
    db.flush()

    record_audit(
        db=db,
        action=AuditAction.CREATE,
        table_name="licenses",
        record_id=lic.id,
        user_id=user_id,
        after={
            "product_id": product.id,
            "seats": seats,
            "start_date": start_date,
            "expiry_date": expiry_date,
            "contract_id": contract.id,
            "contract_line_id": line.id,
        },
        ip_address=ip_address,
    )

    sync_contract_delivery_status(db, contract.id)
    db.flush()
    return lic
