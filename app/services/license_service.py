"""Dịch vụ nghiệp vụ Quản lý Bản quyền / License (Phase 4 - FR-12)."""

from __future__ import annotations

import datetime as dt
from typing import Any
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.audit import record_audit
from app.enums import AuditAction, PersonStatus
from app.models import Asset, License, LicenseAssignment, Person


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

    lic = db.get(License, license_id)
    if not lic or lic.is_deleted:
        raise ValueError(f"License ID {license_id} không tồn tại hoặc đã bị xoá")

    # Kiểm tra trùng lặp trên thiết bị
    if asset_id:
        asset = db.get(Asset, asset_id)
        if not asset or asset.is_deleted:
            raise ValueError(f"Thiết bị #{asset_id} không tồn tại hoặc đã bị xoá")
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

    eff_assigned_at = assigned_at or dt.date.today()
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

    eff_removed_at = removed_at or dt.date.today()
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
