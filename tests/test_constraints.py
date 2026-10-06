"""CỔNG KIỂM SOÁT G2 - ràng buộc toàn vẹn ở tầng database.

Mỗi test ở đây cố tình vi phạm một quy tắc trong BRD mục "Quy tắc toàn vẹn bắt
buộc có trong DB" và yêu cầu PostgreSQL chặn lại. Bộ test này phải XANH trước
khi viết bất kỳ màn hình nào.

Vì sao test ở tầng DB chứ không phải tầng ứng dụng: tầng ứng dụng sẽ bị đi vòng
qua. IT có chuỗi kết nối và sẽ sửa dữ liệu bằng psql lúc gấp. Ràng buộc nào chỉ
nằm trong Python thì sớm muộn cũng bị phá.

KHÔNG xoá hay nới lỏng test nào trong file này để code chạy được. Nếu một test
đỏ, cái sai là code chứ không phải test.
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from app import models as m
from app.enums import AuditAction

TODAY = dt.date(2026, 10, 6)
YESTERDAY = TODAY - dt.timedelta(days=1)


def _violates(db: Session, obj) -> None:
    """Thêm obj và yêu cầu DB từ chối."""
    db.add(obj)
    with pytest.raises((IntegrityError, DBAPIError)):
        db.flush()
    db.rollback()


# ===========================================================================
# 1. Một thiết bị chỉ được cho mượn một lần tại một thời điểm
# ===========================================================================


def test_asset_cannot_be_loaned_twice_at_once(db: Session, seed):
    """Đây là lỗi mà `UNIQUE (asset_id, returned_at)` KHÔNG bắt được.

    Trong PostgreSQL NULL != NULL, nên UniqueConstraint cho phép vô số dòng
    cùng asset_id với returned_at = NULL. Phải là partial unique index.
    """
    db.add(
        m.Assignment(
            asset_id=seed["asset"].id,
            person_id=seed["person"].id,
            borrowed_at=YESTERDAY,
        )
    )
    db.flush()

    _violates(
        db,
        m.Assignment(
            asset_id=seed["asset"].id,
            person_id=seed["person_b"].id,
            borrowed_at=TODAY,
        ),
    )


def test_asset_can_be_loaned_again_after_return(db: Session, seed):
    """Trả rồi thì cho mượn lại được - ràng buộc không được chặt quá."""
    db.add(
        m.Assignment(
            asset_id=seed["asset"].id,
            person_id=seed["person"].id,
            borrowed_at=YESTERDAY,
            returned_at=TODAY,
        )
    )
    db.flush()
    db.add(
        m.Assignment(
            asset_id=seed["asset"].id,
            person_id=seed["person_b"].id,
            borrowed_at=TODAY,
        )
    )
    db.flush()  # không được lỗi


# ===========================================================================
# 2. Một thẻ chỉ được cho mượn một lần tại một thời điểm
# ===========================================================================


def test_card_cannot_be_loaned_twice_at_once(db: Session, seed):
    db.add(
        m.CardLoan(
            card_id=seed["card"].id,
            external_name="Nhan vien kho",
            external_company="倉庫管理業者",
            borrowed_at=YESTERDAY,
        )
    )
    db.flush()
    _violates(
        db,
        m.CardLoan(
            card_id=seed["card"].id,
            external_name="Nhan vien ve sinh",
            borrowed_at=TODAY,
        ),
    )


# ===========================================================================
# 3. Một license không gán hai lần cho cùng một máy / cùng một người
# ===========================================================================


def test_license_cannot_be_double_assigned_to_same_asset(db: Session, seed):
    db.add(
        m.LicenseAssignment(
            license_id=seed["license"].id,
            asset_id=seed["asset"].id,
            assigned_at=YESTERDAY,
        )
    )
    db.flush()
    _violates(
        db,
        m.LicenseAssignment(
            license_id=seed["license"].id,
            asset_id=seed["asset"].id,
            assigned_at=TODAY,
        ),
    )


def test_license_can_be_reassigned_after_removal(db: Session, seed):
    """Gỡ rồi gán lại được. Thiết kế của Gemini chặn luôn trường hợp này."""
    db.add(
        m.LicenseAssignment(
            license_id=seed["license"].id,
            asset_id=seed["asset"].id,
            assigned_at=YESTERDAY,
            removed_at=TODAY,
        )
    )
    db.flush()
    db.add(
        m.LicenseAssignment(
            license_id=seed["license"].id,
            asset_id=seed["asset"].id,
            assigned_at=TODAY,
        )
    )
    db.flush()  # không được lỗi


# ===========================================================================
# 4. Gán license phải có máy hoặc người
# ===========================================================================


def test_license_assignment_needs_a_target(db: Session, seed):
    _violates(
        db,
        m.LicenseAssignment(license_id=seed["license"].id, assigned_at=TODAY),
    )


# ===========================================================================
# 5. Mượn thẻ phải có nhân viên hoặc tên người ngoài
# ===========================================================================


def test_card_loan_needs_a_borrower(db: Session, seed):
    _violates(db, m.CardLoan(card_id=seed["card"].id, borrowed_at=TODAY))


def test_card_loan_rejects_blank_external_name(db: Session, seed):
    """Chuỗi rỗng hoặc toàn khoảng trắng không tính là có người mượn."""
    _violates(
        db,
        m.CardLoan(
            card_id=seed["card"].id, external_name="   ", borrowed_at=TODAY
        ),
    )


# ===========================================================================
# 6. Ngày trả không được trước ngày mượn
# ===========================================================================


def test_return_date_cannot_precede_borrow_date(db: Session, seed):
    _violates(
        db,
        m.Assignment(
            asset_id=seed["asset"].id,
            person_id=seed["person"].id,
            borrowed_at=TODAY,
            returned_at=YESTERDAY,
        ),
    )


def test_card_return_date_cannot_precede_borrow_date(db: Session, seed):
    _violates(
        db,
        m.CardLoan(
            card_id=seed["card"].id,
            external_name="X",
            borrowed_at=TODAY,
            returned_at=YESTERDAY,
        ),
    )


# ===========================================================================
# 7. Ngày hết hạn không được trước ngày bắt đầu; seats phải dương
# ===========================================================================


def test_expiry_cannot_precede_start(db: Session, seed):
    _violates(
        db,
        m.License(
            product_id=seed["product"].id,
            seats=5,
            start_date=TODAY,
            expiry_date=YESTERDAY,
        ),
    )


def test_seats_must_be_positive(db: Session, seed):
    _violates(db, m.License(product_id=seed["product"].id, seats=0))


def test_contract_line_qty_must_be_positive(db: Session, seed):
    contract = m.Contract(code="KHCM-2510-0130")
    db.add(contract)
    db.flush()
    _violates(
        db,
        m.ContractLine(contract_id=contract.id, item_type="PC 16 inch", qty_ordered=0),
    )


# ===========================================================================
# 8. Trạng thái phải nằm trong tập ENUM
# ===========================================================================


def test_status_rejects_free_text(db: Session, seed):
    """Sheet Excel cũ có "Delivered to Mr. Chuong" ở cột trạng thái.

    ENUM native làm chuyện đó không lặp lại được, kể cả khi ghi bằng SQL tay.
    """
    from sqlalchemy import text as sql

    with pytest.raises(DBAPIError):
        db.execute(
            sql("UPDATE assets SET status = 'Delivered to Mr. Chuong' WHERE id = :i"),
            {"i": seed["asset"].id},
        )
    db.rollback()


def test_phone_extension_rejects_na_literal(db: Session, seed):
    """Excel cũ ghi 'N/A'. Trong DB phải là ô trống."""
    _violates(
        db,
        m.Phone(device_name="TELG101", device_type="IP_PHONE", extension_number="N/A"),
    )


# ===========================================================================
# 9. Duy nhất chỉ tính trên bản ghi chưa xoá mềm
# ===========================================================================


def test_serial_unique_among_alive_rows(db: Session, seed):
    _violates(db, m.Asset(serial="SN-0001", category_id=seed["cat"].id))


def test_serial_can_be_reused_after_soft_delete(db: Session, seed):
    """Nhập nhầm serial, xoá mềm, rồi nhập lại đúng serial đó - phải cho phép."""
    seed["asset"].is_deleted = True
    seed["asset"].deleted_at = dt.datetime.now(dt.timezone.utc)
    seed["asset"].delete_reason = "Nhap trung"
    db.flush()
    db.add(m.Asset(serial="SN-0001", category_id=seed["cat"].id))
    db.flush()  # không được lỗi


def test_staff_code_unique_among_alive_rows(db: Session, seed):
    _violates(db, m.Person(staff_code="TVC00001", full_name="Trung ma"))


# ===========================================================================
# 10. Xoá mềm phải nhất quán và bắt buộc có lý do
# ===========================================================================


def test_soft_delete_requires_reason(db: Session, seed):
    seed["asset"].is_deleted = True
    seed["asset"].deleted_at = dt.datetime.now(dt.timezone.utc)
    # thiếu delete_reason
    with pytest.raises((IntegrityError, DBAPIError)):
        db.flush()
    db.rollback()


def test_soft_delete_rejects_blank_reason(db: Session, seed):
    seed["asset"].is_deleted = True
    seed["asset"].deleted_at = dt.datetime.now(dt.timezone.utc)
    seed["asset"].delete_reason = "   "
    with pytest.raises((IntegrityError, DBAPIError)):
        db.flush()
    db.rollback()


# ===========================================================================
# 11. Audit log không sửa được, không xoá được - kể cả bằng SQL tay
# ===========================================================================


def _add_audit(db: Session, seed) -> int:
    log = m.AuditLog(
        user_id=seed["user"].id,
        table_name="assets",
        record_id=seed["asset"].id,
        action=AuditAction.CREATE,
        before_after={"after": {"serial": "SN-0001"}},
    )
    db.add(log)
    db.flush()
    return log.id


def test_audit_log_cannot_be_updated(db: Session, seed):
    from sqlalchemy import text as sql

    log_id = _add_audit(db, seed)
    with pytest.raises(DBAPIError):
        db.execute(
            sql("UPDATE audit_logs SET action = 'UPDATE' WHERE id = :i"), {"i": log_id}
        )
    db.rollback()


def test_audit_log_cannot_be_deleted(db: Session, seed):
    from sqlalchemy import text as sql

    log_id = _add_audit(db, seed)
    with pytest.raises(DBAPIError):
        db.execute(sql("DELETE FROM audit_logs WHERE id = :i"), {"i": log_id})
    db.rollback()


def test_audit_log_can_be_inserted_and_read(db: Session, seed):
    log_id = _add_audit(db, seed)
    assert db.get(m.AuditLog, log_id) is not None


# ===========================================================================
# 12. Tài sản phải có ít nhất một thứ để nhận dạng
# ===========================================================================


def test_asset_needs_an_identifier(db: Session, seed):
    _violates(db, m.Asset(category_id=seed["cat"].id, model="Dell Pro 16"))


# ===========================================================================
# 13. Số đã nhận được ĐẾM, không gõ tay
# ===========================================================================


def test_contract_line_has_no_delivered_qty_column(db: Session):
    """Chốt chặn chống trôi thiết kế.

    Nếu ai đó (hoặc một agent code) thêm lại delivered_qty / remaining_qty vào
    contract_lines, test này đỏ. Số đã nhận phải đếm từ assets.contract_line_id -
    cột gõ tay chính là nguồn sai lệch của sheet "PC_Qty summary".
    """
    cols = {c.name for c in m.ContractLine.__table__.columns}
    assert "delivered_qty" not in cols
    assert "remaining_qty" not in cols


def test_received_count_derives_from_assets(db: Session, seed):
    from sqlalchemy import func, select

    contract = m.Contract(code="KHCM-2408-0113")
    db.add(contract)
    db.flush()
    line = m.ContractLine(
        contract_id=contract.id, item_type="PC 16 inch", qty_ordered=10
    )
    db.add(line)
    db.flush()

    for i in range(3):
        db.add(
            m.Asset(
                serial=f"SN-X{i}", category_id=seed["cat"].id, contract_line_id=line.id
            )
        )
    db.flush()

    received = db.scalar(
        select(func.count())
        .select_from(m.Asset)
        .where(m.Asset.contract_line_id == line.id, m.Asset.is_deleted.is_(False))
    )
    assert received == 3
    assert line.qty_ordered - received == 7


# ===========================================================================
# 14. Mật khẩu KHÔNG nằm trong bảng persons
# ===========================================================================


def test_persons_table_holds_no_secrets(db: Session):
    """Chốt chặn: SELECT * trên persons không bao giờ được kéo theo mật khẩu."""
    cols = {c.name for c in m.Person.__table__.columns}
    forbidden = {"password", "pc_password", "email_password",
                 "pc_password_enc", "email_password_enc"}
    assert not (cols & forbidden), f"Mật khẩu bị lẫn vào persons: {cols & forbidden}"


def test_no_plaintext_password_columns_anywhere(db: Session):
    """Mọi cột liên quan mật khẩu phải là dạng mã hoá hoặc băm."""
    from sqlalchemy import LargeBinary, Text

    allowed = {"password_hash", "pc_password_enc", "email_password_enc",
               "license_key_enc", "pc_password_note", "email_password_note"}
    for table in m.Base.metadata.tables.values():
        for col in table.columns:
            if "password" in col.name or "license_key" in col.name:
                assert col.name in allowed, (
                    f"Cột đáng ngờ {table.name}.{col.name} - "
                    "mật khẩu phải mã hoá (_enc) hoặc băm (_hash)"
                )
                if col.name.endswith("_enc"):
                    assert isinstance(col.type, LargeBinary), (
                        f"{table.name}.{col.name} phải là BYTEA"
                    )
                if col.name == "password_hash":
                    assert isinstance(col.type, Text)
