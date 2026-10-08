"""Dịch vụ nghiệp vụ quản lý Nhân sự & Hồ sơ Tổng hợp (Person Service - FR-05, FR-11).

Quy tắc nghiệp vụ từ BRD và GEMINI.md:
- Thêm/sửa nhân viên: kiểm tra trùng mã TVC (staff_code), user_login_id, email trên các bản ghi sống.
- Xóa mềm nhân viên: bắt buộc có delete_reason. Chặn xóa nếu nhân viên đang giữ bất kỳ tài sản IT, thẻ ra vào hoặc license nào.
- Hồ sơ tổng hợp (FR-11): tổng hợp toàn bộ thiết bị, license, thẻ mà nhân viên đang giữ và đã từng giữ.
- Ghi nhận audit log đầy đủ cho CREATE, UPDATE, DELETE.
"""

from __future__ import annotations

import datetime as dt
from typing import Any
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.audit import record_audit
from app.enums import AuditAction, PersonStatus
from app.models import (
    AccessCard,
    Asset,
    Assignment,
    CardLoan,
    Department,
    License,
    LicenseAssignment,
    Person,
)


def _person_to_dict(person: Person) -> dict[str, Any]:
    return {
        "id": person.id,
        "staff_code": person.staff_code,
        "user_login_id": person.user_login_id,
        "full_name": person.full_name,
        "department_id": person.department_id,
        "email": person.email,
        "status": person.status.value if isinstance(person.status, PersonStatus) else str(person.status),
        "start_working_date": person.start_working_date.isoformat() if person.start_working_date else None,
        "note": person.note,
        "is_deleted": person.is_deleted,
    }


def get_person(db: Session, person_id: int) -> Person | None:
    return db.scalar(
        select(Person)
        .options(selectinload(Person.department))
        .where(Person.id == person_id, Person.is_deleted.is_(False))
    )


def create_person(
    db: Session,
    data: dict[str, Any],
    user_id: int | None = None,
    ip_address: str | None = None,
) -> Person:
    """Tạo mới hồ sơ nhân sự."""
    staff_code = (data.get("staff_code") or "").strip()
    if not staff_code:
        raise ValueError("Mã nhân viên (staff_code) không được để trống.")

    full_name = (data.get("full_name") or "").strip()
    if not full_name:
        raise ValueError("Họ và tên nhân viên không được để trống.")

    user_login_id = (data.get("user_login_id") or "").strip() or None
    email = (data.get("email") or "").strip() or None

    # Kiểm tra trùng lặp trên các bản ghi sống
    dup = db.scalar(select(Person).where(Person.staff_code == staff_code, Person.is_deleted.is_(False)))
    if dup:
        raise ValueError(f"Mã nhân viên '{staff_code}' đã tồn tại trong hệ thống.")

    if user_login_id:
        dup = db.scalar(select(Person).where(Person.user_login_id == user_login_id, Person.is_deleted.is_(False)))
        if dup:
            raise ValueError(f"Tài khoản đăng nhập '{user_login_id}' đã tồn tại trong hệ thống.")

    if email:
        dup = db.scalar(select(Person).where(Person.email == email, Person.is_deleted.is_(False)))
        if dup:
            raise ValueError(f"Email '{email}' đã tồn tại trong hệ thống.")

    status_val = data.get("status") or PersonStatus.ACTIVE
    if isinstance(status_val, str):
        status_val = PersonStatus(status_val)

    start_date = data.get("start_working_date")
    if isinstance(start_date, str) and start_date.strip():
        start_date = dt.date.fromisoformat(start_date.strip())

    person = Person(
        staff_code=staff_code,
        user_login_id=user_login_id,
        full_name=full_name,
        department_id=data.get("department_id"),
        email=email,
        status=status_val,
        start_working_date=start_date,
        note=(data.get("note") or "").strip() or None,
        created_by=user_id,
        updated_by=user_id,
    )
    db.add(person)
    db.flush()

    record_audit(
        db=db,
        action=AuditAction.CREATE,
        table_name="persons",
        record_id=person.id,
        user_id=user_id,
        after=_person_to_dict(person),
        ip_address=ip_address,
    )
    db.flush()
    return person


def update_person(
    db: Session,
    person_id: int,
    data: dict[str, Any],
    user_id: int | None = None,
    ip_address: str | None = None,
) -> Person:
    """Cập nhật thông tin nhân viên."""
    person = db.scalar(select(Person).where(Person.id == person_id, Person.is_deleted.is_(False)))
    if not person:
        raise ValueError(f"Không tìm thấy nhân viên với ID {person_id}.")

    before_dict = _person_to_dict(person)

    if "staff_code" in data:
        new_code = (data["staff_code"] or "").strip()
        if not new_code:
            raise ValueError("Mã nhân viên không được để trống.")
        if new_code != person.staff_code:
            dup = db.scalar(select(Person).where(Person.staff_code == new_code, Person.is_deleted.is_(False)))
            if dup:
                raise ValueError(f"Mã nhân viên '{new_code}' đã tồn tại trong hệ thống.")
            person.staff_code = new_code

    if "email" in data:
        new_email = (data["email"] or "").strip() or None
        if new_email and new_email != person.email:
            dup = db.scalar(select(Person).where(Person.email == new_email, Person.is_deleted.is_(False)))
            if dup:
                raise ValueError(f"Email '{new_email}' đã tồn tại trong hệ thống.")
        person.email = new_email

    if "user_login_id" in data:
        new_uid = (data["user_login_id"] or "").strip() or None
        if new_uid and new_uid != person.user_login_id:
            dup = db.scalar(select(Person).where(Person.user_login_id == new_uid, Person.is_deleted.is_(False)))
            if dup:
                raise ValueError(f"Tài khoản đăng nhập '{new_uid}' đã tồn tại trong hệ thống.")
        person.user_login_id = new_uid

    if "full_name" in data and data["full_name"]:
        person.full_name = data["full_name"].strip()

    if "department_id" in data:
        person.department_id = data["department_id"]

    if "status" in data and data["status"]:
        val = data["status"]
        person.status = PersonStatus(val) if isinstance(val, str) else val

    if "start_working_date" in data:
        val = data["start_working_date"]
        person.start_working_date = dt.date.fromisoformat(val) if isinstance(val, str) and val.strip() else val

    if "note" in data:
        person.note = (data["note"] or "").strip() or None

    person.updated_by = user_id
    person.updated_at = dt.datetime.now(dt.timezone.utc)
    db.flush()

    record_audit(
        db=db,
        action=AuditAction.UPDATE,
        table_name="persons",
        record_id=person.id,
        user_id=user_id,
        before=before_dict,
        after=_person_to_dict(person),
        ip_address=ip_address,
    )
    db.flush()
    return person


def soft_delete_person(
    db: Session,
    person_id: int,
    delete_reason: str,
    user_id: int | None = None,
    ip_address: str | None = None,
) -> Person:
    """Xóa mềm nhân viên. Chặn xóa nếu nhân viên đang giữ tài sản/thẻ/license."""
    clean_reason = (delete_reason or "").strip()
    if not clean_reason:
        raise ValueError("Lý do xóa không được để trống (bắt buộc nhập theo GEMINI.md).")

    person = db.scalar(select(Person).where(Person.id == person_id, Person.is_deleted.is_(False)))
    if not person:
        raise ValueError(f"Không tìm thấy nhân viên với ID {person_id}.")

    # 1. Kiểm tra tài sản đang giữ
    active_asset_asgn = db.scalar(
        select(Assignment).where(
            Assignment.person_id == person_id,
            Assignment.returned_at.is_(None),
            Assignment.is_deleted.is_(False),
        )
    )
    if active_asset_asgn:
        raise ValueError("Không thể xóa nhân viên đang giữ thiết bị IT. Hãy thu hồi thiết bị trước khi xóa.")

    # 2. Kiểm tra thẻ ra vào đang mượn
    active_card_loan = db.scalar(
        select(CardLoan).where(
            CardLoan.person_id == person_id,
            CardLoan.returned_at.is_(None),
            CardLoan.is_deleted.is_(False),
        )
    )
    if active_card_loan:
        raise ValueError("Không thể xóa nhân viên đang mượn thẻ ra vào. Hãy thu hồi thẻ trước khi xóa.")

    # 3. Kiểm tra license đang được cấp
    active_lic_asgn = db.scalar(
        select(LicenseAssignment).where(
            LicenseAssignment.person_id == person_id,
            LicenseAssignment.removed_at.is_(None),
            LicenseAssignment.is_deleted.is_(False),
        )
    )
    if active_lic_asgn:
        raise ValueError("Không thể xóa nhân viên đang được cấp bản quyền phần mềm. Hãy thu hồi license trước khi xóa.")

    before_dict = _person_to_dict(person)

    person.is_deleted = True
    person.delete_reason = clean_reason
    person.deleted_by = user_id
    person.deleted_at = dt.datetime.now(dt.timezone.utc)
    db.flush()

    record_audit(
        db=db,
        action=AuditAction.DELETE,
        table_name="persons",
        record_id=person.id,
        user_id=user_id,
        before=before_dict,
        after=_person_to_dict(person),
        ip_address=ip_address,
    )
    db.flush()
    return person


def get_person_profile(db: Session, person_id: int) -> dict[str, Any] | None:
    """Tổng hợp toàn bộ hồ sơ sở hữu của một nhân sự (FR-11)."""
    person = get_person(db, person_id)
    if not person:
        return None

    # 1. Thiết bị đang giữ & lịch sử
    asset_asgns = db.scalars(
        select(Assignment)
        .options(selectinload(Assignment.asset))
        .where(Assignment.person_id == person_id, Assignment.is_deleted.is_(False))
        .order_by(Assignment.borrowed_at.desc())
    ).all()

    active_assets = [a.asset for a in asset_asgns if a.returned_at is None and a.asset]
    past_asset_asgns = [a for a in asset_asgns if a.returned_at is not None]

    # 2. License đang dùng & lịch sử
    lic_asgns = db.scalars(
        select(LicenseAssignment)
        .options(selectinload(LicenseAssignment.license).selectinload(License.product))
        .where(LicenseAssignment.person_id == person_id, LicenseAssignment.is_deleted.is_(False))
        .order_by(LicenseAssignment.assigned_at.desc())
    ).all()

    active_licenses = [la for la in lic_asgns if la.removed_at is None]
    past_licenses = [la for la in lic_asgns if la.removed_at is not None]

    # 3. Thẻ ra vào đang mượn & lịch sử
    card_loans = db.scalars(
        select(CardLoan)
        .options(selectinload(CardLoan.card))
        .where(CardLoan.person_id == person_id, CardLoan.is_deleted.is_(False))
        .order_by(CardLoan.borrowed_at.desc())
    ).all()

    active_cards = [cl for cl in card_loans if cl.returned_at is None]
    past_cards = [cl for cl in card_loans if cl.returned_at is not None]

    return {
        "person": person,
        "active_assets": active_assets,
        "past_asset_assignments": past_asset_asgns,
        "active_licenses": active_licenses,
        "past_licenses": past_licenses,
        "active_cards": active_cards,
        "past_cards": past_cards,
    }
