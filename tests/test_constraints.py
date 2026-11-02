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
