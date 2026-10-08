"""Kiểm thử tầng nghiệp vụ License, Thẻ ra vào và Hợp đồng (Phase 4 - FR-12, FR-13, FR-14)."""

from __future__ import annotations

import datetime as dt
import pytest
from sqlalchemy.orm import Session

from app.enums import CardStatus
from app.models import AccessCard, Asset, Contract, ContractLine
from app.services.card_service import (
    get_active_card_loan,
    loan_card,
    return_card,
)
from app.services.contract_service import get_contract_summary
from app.services.license_service import (
    assign_license,
    get_license_seats_summary,
    revoke_license,
)

TODAY = dt.date(2026, 10, 8)
YESTERDAY = TODAY - dt.timedelta(days=1)


# =============================================================================
# 1. License Service Tests
# =============================================================================

def test_assign_license_to_person_and_asset(db: Session, seed):
    lic = seed["license"]  # 13 seats
    person = seed["person"]
    asset = seed["asset"]
    user_id = seed["user"].id

    asgn = assign_license(
        db=db,
        license_id=lic.id,
        person_id=person.id,
        asset_id=asset.id,
        assigned_at=TODAY,
        note="Cấp Office cho máy nhân viên",
        user_id=user_id,
    )
    assert asgn.id is not None
    assert asgn.removed_at is None

    summary = get_license_seats_summary(db, lic.id)
    assert summary["assigned_seats"] == 1
    assert summary["remaining_seats"] == 12


def test_assign_license_requires_person_or_asset(db: Session, seed):
    lic = seed["license"]
    with pytest.raises(ValueError, match="phải được gán cho máy tính hoặc nhân viên"):
        assign_license(db=db, license_id=lic.id, person_id=None, asset_id=None)


def test_cannot_assign_same_license_to_same_asset_twice(db: Session, seed):
    lic = seed["license"]
    asset = seed["asset"]
    user_id = seed["user"].id

    assign_license(db, lic.id, asset_id=asset.id, user_id=user_id)

    with pytest.raises(ValueError, match="đã được gán bản quyền này"):
        assign_license(db, lic.id, asset_id=asset.id, user_id=user_id)


def test_revoke_license_success(db: Session, seed):
    lic = seed["license"]
    person = seed["person"]
    user_id = seed["user"].id

    asgn = assign_license(db, lic.id, person_id=person.id, user_id=user_id)
    revoked = revoke_license(db, asgn.id, removed_at=TODAY, note="Nhân viên thôi việc", user_id=user_id)

    assert revoked.removed_at == TODAY
    summary = get_license_seats_summary(db, lic.id)
    assert summary["assigned_seats"] == 0
    assert summary["remaining_seats"] == 13


# =============================================================================
# 2. Card Service Tests
# =============================================================================

def test_loan_card_to_person(db: Session, seed):
    card = seed["card"]
    person = seed["person"]
    user_id = seed["user"].id

    loan = loan_card(
        db=db,
        card_id=card.id,
        person_id=person.id,
        borrowed_at=TODAY,
        expected_return_at=TODAY + dt.timedelta(days=7),
        note="Cho mượn thẻ vào văn phòng",
        user_id=user_id,
    )
    assert loan.id is not None
    assert loan.returned_at is None

    active = get_active_card_loan(db, card.id)
    assert active is not None
    assert active.id == loan.id


def test_loan_card_to_external_contractor(db: Session, seed):
    card2 = AccessCard(card_no="CARD-EXT-002", status=CardStatus.IN_STOCK)
    db.add(card2)
    db.flush()

    loan = loan_card(
        db=db,
        card_id=card2.id,
        external_name="Yamada Taro",
        external_company="Tokyo Systems",
        borrowed_at=TODAY,
    )
    assert loan.external_name == "Yamada Taro"
    assert loan.person_id is None


def test_cannot_loan_card_already_borrowed(db: Session, seed):
    card = seed["card"]
    person = seed["person"]

    loan_card(db, card.id, person_id=person.id, borrowed_at=TODAY)

    with pytest.raises(ValueError, match="đang được cho mượn"):
        loan_card(db, card.id, external_name="Nguoi khac", borrowed_at=TODAY)


def test_return_card_success(db: Session, seed):
    card = seed["card"]
    person = seed["person"]

    loan_card(db, card.id, person_id=person.id, borrowed_at=YESTERDAY)
    returned_loan = return_card(db, card.id, returned_at=TODAY, note="Đã trả nguyên vẹn")

    assert returned_loan.returned_at == TODAY
    assert get_active_card_loan(db, card.id) is None


# =============================================================================
# 3. Contract Delivery Summary Tests
# =============================================================================

def test_contract_summary_counts_from_assets(db: Session, seed):
    # Tạo hợp đồng có 1 dòng đặt 5 chiếc laptop
    contract = Contract(code="KHCM-2026-TEST", vendor_name="KDDI Vietnam")
    db.add(contract)
    db.flush()

    line = ContractLine(contract_id=contract.id, item_type="Laptop", qty_ordered=5)
    db.add(line)
    db.flush()

    # Nhận 2 thiết bị liên kết với line_id
    cat = seed["cat"]
    a1 = Asset(category_id=cat.id, contract_line_id=line.id, serial="SN-C-01")
    a2 = Asset(category_id=cat.id, contract_line_id=line.id, serial="SN-C-02")
    db.add_all([a1, a2])
    db.flush()

    summary = get_contract_summary(db, contract.id)
    assert summary["contract"].id == contract.id
    assert len(summary["lines"]) == 1
    line_summary = summary["lines"][0]
    assert line_summary["qty_ordered"] == 5
    assert line_summary["qty_delivered"] == 2
    assert line_summary["qty_remaining"] == 3
    assert line_summary["status"] == "PARTIAL"
