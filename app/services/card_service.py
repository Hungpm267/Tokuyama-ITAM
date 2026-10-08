"""Dịch vụ nghiệp vụ Quản lý Thẻ ra vào và Mượn-trả thẻ (Phase 4 - FR-13)."""

from __future__ import annotations

import datetime as dt
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import record_audit
from app.enums import AuditAction, CardStatus
from app.models import AccessCard, CardLoan


def get_active_card_loan(db: Session, card_id: int) -> CardLoan | None:
    """Tìm lượt mượn đang mở (chưa trả) của một thẻ."""
    return db.scalar(
        select(CardLoan).where(
            CardLoan.card_id == card_id,
            CardLoan.returned_at.is_(None),
            CardLoan.is_deleted.is_(False),
        )
    )


def loan_card(
    db: Session,
    card_id: int,
    person_id: int | None = None,
    external_name: str | None = None,
    external_company: str | None = None,
    borrowed_at: dt.date | None = None,
    expected_return_at: dt.date | None = None,
    purpose: str | None = None,
    note: str | None = None,
    user_id: int | None = None,
) -> CardLoan:
    """Cho mượn thẻ ra vào (nhân viên nội bộ HOẶC khách/nhà thầu bên ngoài).
    
    Quy tắc:
    - Bắt buộc có person_id hoặc external_name (có tên hợp lệ).
    - Thẻ không thể cho mượn nếu đang có người mượn hoặc hỏng/mất.
    - Cập nhật trạng thái thẻ sang BORROWED.
    - Ghi audit log CREATE.
    """
    clean_ext_name = external_name.strip() if external_name and external_name.strip() else None
    clean_ext_company = external_company.strip() if external_company and external_company.strip() else None

    if not person_id and not clean_ext_name:
        raise ValueError("Người mượn thẻ phải là nhân viên hoặc có họ tên đối tác bên ngoài")

    card = db.get(AccessCard, card_id)
    if not card or card.is_deleted:
        raise ValueError(f"Thẻ ID {card_id} không tồn tại hoặc đã bị xoá")

    if card.status in (CardStatus.LOST, CardStatus.DAMAGED):
        raise ValueError(f"Thẻ '{card.card_no}' đang ở trạng thái {card.status.value}, không thể cho mượn")

    active_loan = get_active_card_loan(db, card_id)
    if active_loan:
        raise ValueError(f"Thẻ '{card.card_no}' đang được cho mượn")

    eff_borrowed_at = borrowed_at or dt.date.today()
    if expected_return_at and expected_return_at < eff_borrowed_at:
        raise ValueError("Ngày dự kiến trả không được trước ngày mượn thẻ")

    combined_purpose = purpose or note

    loan = CardLoan(
        card_id=card_id,
        person_id=person_id,
        external_name=clean_ext_name,
        external_company=clean_ext_company,
        purpose=combined_purpose,
        borrowed_at=eff_borrowed_at,
        expected_return_at=expected_return_at,
    )
    db.add(loan)

    # Cập nhật trạng thái thẻ
    card.status = CardStatus.BORROWED
    db.flush()

    record_audit(
        db=db,
        action=AuditAction.CREATE,
        table_name="card_loans",
        record_id=loan.id,
        user_id=user_id,
        after={
            "card_id": card_id,
            "person_id": person_id,
            "external_name": clean_ext_name,
            "external_company": clean_ext_company,
            "borrowed_at": eff_borrowed_at,
        },
    )

    return loan


def return_card(
    db: Session,
    card_id: int,
    returned_at: dt.date | None = None,
    note: str | None = None,
    user_id: int | None = None,
) -> CardLoan:
    """Ghi nhận trả thẻ ra vào (Rule 7: không xoá, chỉ đóng bằng returned_at)."""
    card = db.get(AccessCard, card_id)
    if not card or card.is_deleted:
        raise ValueError(f"Thẻ ID {card_id} không tồn tại hoặc đã bị xoá")

    loan = get_active_card_loan(db, card_id)
    if not loan:
        raise ValueError(f"Thẻ '{card.card_no}' hiện không có lượt mượn nào đang mở")

    eff_returned_at = returned_at or dt.date.today()
    if eff_returned_at < loan.borrowed_at:
        raise ValueError("Ngày trả thẻ không được trước ngày mượn")

    before_state = {
        "returned_at": loan.returned_at,
        "purpose": loan.purpose,
    }

    loan.returned_at = eff_returned_at
    if note:
        loan.purpose = f"{loan.purpose or ''}\n[Trả thẻ: {note}]".strip()

    card.status = CardStatus.IN_STOCK
    db.flush()

    record_audit(
        db=db,
        action=AuditAction.UPDATE,
        table_name="card_loans",
        record_id=loan.id,
        user_id=user_id,
        before=before_state,
        after={
            "returned_at": eff_returned_at,
            "purpose": loan.purpose,
        },
    )

    return loan
