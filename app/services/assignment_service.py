"""Dịch vụ nghiệp vụ Bàn giao & Thu hồi Thiết bị (Assignment Service - FR-10).

Quy tắc nghiệp vụ cốt lõi từ GEMINI.md:
- Mỗi thiết bị tại một thời điểm chỉ được bàn giao cho đúng 1 người (partial index returned_at IS NULL).
- Lịch sử bàn giao KHÔNG XOÁ, chỉ đóng bằng ngày kết thúc (returned_at).
- Khi bàn giao -> tự động chuyển trạng thái thiết bị sang IN_USE.
- Khi thu hồi -> chuyển trạng thái thiết bị về IN_STOCK (hoặc REPAIR nếu máy hỏng).
- Ghi audit log liên kết cả hai bảng: assignments và assets.
"""

from __future__ import annotations

import datetime as dt
from typing import Any
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.audit import record_audit
from app.core.clock import today_local
from app.enums import AssetStatus, AuditAction, PersonStatus
from app.models import Asset, Assignment, Person


#: Trạng thái được phép đặt cho thiết bị ngay khi thu hồi.
RETURNABLE_STATUSES = frozenset({AssetStatus.IN_STOCK, AssetStatus.REPAIR, AssetStatus.DISPOSED})


def _assignment_to_dict(asgn: Assignment) -> dict[str, Any]:
    """Chuyển đổi thực thể Assignment thành dict để ghi audit log."""
    return {
        "id": asgn.id,
        "asset_id": asgn.asset_id,
        "person_id": asgn.person_id,
        "borrowed_at": asgn.borrowed_at.isoformat() if asgn.borrowed_at else None,
        "returned_at": asgn.returned_at.isoformat() if asgn.returned_at else None,
        "note": asgn.note,
        "is_deleted": asgn.is_deleted,
    }


def get_active_assignment(db: Session, asset_id: int) -> Assignment | None:
    """Lấy bản ghi bàn giao đang mở (chưa trả) của một thiết bị."""
    return db.scalar(
        select(Assignment)
        .options(selectinload(Assignment.person), selectinload(Assignment.asset))
        .where(
            Assignment.asset_id == asset_id,
            Assignment.returned_at.is_(None),
            Assignment.is_deleted.is_(False),
        )
    )


def get_asset_assignment_history(db: Session, asset_id: int) -> list[Assignment]:
    """Lấy toàn bộ lịch sử bàn giao của một thiết bị, sắp xếp mới nhất lên đầu."""
    return db.scalars(
        select(Assignment)
        .options(selectinload(Assignment.person))
        .where(
            Assignment.asset_id == asset_id,
            Assignment.is_deleted.is_(False),
        )
        .order_by(Assignment.borrowed_at.desc(), Assignment.id.desc())
    ).all()


def get_person_assignment_history(db: Session, person_id: int) -> list[Assignment]:
    """Lấy danh sách thiết bị một nhân viên đang và đã từng mượn."""
    return db.scalars(
        select(Assignment)
        .options(selectinload(Assignment.asset))
        .where(
            Assignment.person_id == person_id,
            Assignment.is_deleted.is_(False),
        )
        .order_by(Assignment.borrowed_at.desc(), Assignment.id.desc())
    ).all()


def assign_asset(
    db: Session,
    asset_id: int,
    person_id: int,
    borrowed_at: dt.date,
    note: str | None = None,
    user_id: int | None = None,
    ip_address: str | None = None,
) -> Assignment:
    """Bàn giao thiết bị cho nhân viên (Assign)."""
    asset = db.scalar(select(Asset).where(Asset.id == asset_id, Asset.is_deleted.is_(False)))
    if not asset:
        raise ValueError(f"Thiết bị với ID {asset_id} không tồn tại hoặc đã bị xóa.")

    if asset.status in (AssetStatus.DISPOSED, AssetStatus.LOST, AssetStatus.REPAIR):
        raise ValueError(f"Không thể bàn giao thiết bị ở trạng thái '{asset.status.value}'.")

    # Kiểm tra xem máy có đang có người sử dụng không
    active = get_active_assignment(db, asset_id)
    if active or asset.status == AssetStatus.IN_USE:
        holder_name = active.person.full_name if (active and active.person) else "người khác"
        raise ValueError(
            f"Thiết bị '{asset.asset_code or asset.serial}' đang có người sử dụng ({holder_name}), "
            "vui lòng thu hồi trước khi bàn giao tiếp."
        )

    # Kiểm tra nhân viên nhận máy
    person = db.scalar(select(Person).where(Person.id == person_id, Person.is_deleted.is_(False)))
    if not person:
        raise ValueError(f"Nhân viên với ID {person_id} không tồn tại hoặc đã bị xóa.")
    if person.status == PersonStatus.RESIGNED:
        raise ValueError(f"Không thể bàn giao thiết bị cho nhân viên đã nghỉ việc ({person.full_name}).")

    # Không cho phép cấp phát trong tương lai
    today = today_local()
    if borrowed_at > today:
        raise ValueError(
            f"Ngày bàn giao ({borrowed_at.strftime('%d/%m/%Y')}) không được vượt quá ngày hiện tại "
            f"({today.strftime('%d/%m/%Y')}). Không được chọn ngày trong tương lai."
        )

    # Kiểm tra trùng lặp thời gian với các lần mượn trước đó
    overlapping_history = db.scalar(
        select(Assignment).where(
            Assignment.asset_id == asset_id,
            Assignment.is_deleted.is_(False),
            Assignment.returned_at.is_not(None),
            Assignment.returned_at > borrowed_at,
        ).order_by(Assignment.returned_at.desc())
    )
    if overlapping_history:
        ret_date_str = overlapping_history.returned_at.strftime("%d/%m/%Y")
        raise ValueError(
            f"Ngày bàn giao ({borrowed_at.strftime('%d/%m/%Y')}) không được trước ngày kết thúc "
            f"của lần mượn trước đó ({ret_date_str})."
        )

    # 1. Tạo bản ghi Assignment
    clean_note = (note or "").strip() or None
    asgn = Assignment(
        asset_id=asset.id,
        person_id=person.id,
        borrowed_at=borrowed_at,
        returned_at=None,
        note=clean_note,
        created_by=user_id,
        updated_by=user_id,
    )
    db.add(asgn)
    db.flush()

    # 2. Cập nhật trạng thái Asset sang IN_USE
    old_asset_status = asset.status
    asset.status = AssetStatus.IN_USE
    asset.updated_by = user_id
    asset.updated_at = dt.datetime.now(dt.timezone.utc)
    db.flush()

    # 3. Ghi audit logs
    record_audit(
        db=db,
        action=AuditAction.CREATE,
        table_name="assignments",
        record_id=asgn.id,
        user_id=user_id,
        after=_assignment_to_dict(asgn),
        ip_address=ip_address,
    )
    record_audit(
        db=db,
        action=AuditAction.UPDATE,
        table_name="assets",
        record_id=asset.id,
        user_id=user_id,
        before={"status": old_asset_status.value},
        after={"status": AssetStatus.IN_USE.value, "assigned_to": person.full_name},
        ip_address=ip_address,
    )
    db.flush()

    return asgn


def return_asset(
    db: Session,
    asset_id: int,
    returned_at: dt.date,
    return_status: AssetStatus = AssetStatus.IN_STOCK,
    note: str | None = None,
    user_id: int | None = None,
    ip_address: str | None = None,
) -> Assignment:
    """Thu hồi thiết bị về kho hoặc chuyển đi sửa chữa (Return)."""
    asset = db.scalar(select(Asset).where(Asset.id == asset_id, Asset.is_deleted.is_(False)))
    if not asset:
        raise ValueError(f"Thiết bị với ID {asset_id} không tồn tại hoặc đã bị xóa.")

    asgn = get_active_assignment(db, asset_id)
    if not asgn:
        raise ValueError(f"Thiết bị '{asset.asset_code or asset.serial}' không có bản ghi bàn giao nào đang mở để thu hồi.")

    if returned_at < asgn.borrowed_at:
        raise ValueError(
            f"Ngày thu hồi ({returned_at.strftime('%d/%m/%Y')}) không được trước ngày bàn giao "
            f"({asgn.borrowed_at.strftime('%d/%m/%Y')})."
        )

    today = today_local()
    if returned_at > today:
        raise ValueError(
            f"Ngày thu hồi ({returned_at.strftime('%d/%m/%Y')}) không được vượt quá ngày hiện tại "
            f"({today.strftime('%d/%m/%Y')}). Không được chọn ngày trong tương lai."
        )

    # Từ chối thay vì âm thầm đổi về IN_STOCK: máy báo mất mà ghi "trong kho"
    # thì lượt sau sẽ có người được bàn giao một chiếc máy không tồn tại.
    if return_status not in RETURNABLE_STATUSES:
        raise ValueError(
            f"Trạng thái sau thu hồi '{return_status.value}' không hợp lệ. "
            "Chỉ chấp nhận: IN_STOCK (về kho), REPAIR (đi sửa), DISPOSED (thanh lý)."
        )

    before_asgn = _assignment_to_dict(asgn)

    # 1. Đóng bản ghi bàn giao bằng ngày trả
    asgn.returned_at = returned_at
    if note and note.strip():
        return_note = f"Thu hồi ({returned_at.strftime('%d/%m/%Y')}): {note.strip()}"
        asgn.note = f"{asgn.note} | {return_note}" if asgn.note else return_note
    asgn.updated_by = user_id
    asgn.updated_at = dt.datetime.now(dt.timezone.utc)
    db.flush()

    # 2. Cập nhật trạng thái Asset
    old_asset_status = asset.status
    asset.status = return_status
    asset.updated_by = user_id
    asset.updated_at = dt.datetime.now(dt.timezone.utc)
    db.flush()

    # 3. Ghi audit logs
    record_audit(
        db=db,
        action=AuditAction.UPDATE,
        table_name="assignments",
        record_id=asgn.id,
        user_id=user_id,
        before=before_asgn,
        after=_assignment_to_dict(asgn),
        ip_address=ip_address,
    )
    record_audit(
        db=db,
        action=AuditAction.UPDATE,
        table_name="assets",
        record_id=asset.id,
        user_id=user_id,
        before={"status": old_asset_status.value},
        after={"status": return_status.value},
        ip_address=ip_address,
    )
    db.flush()

    return asgn
