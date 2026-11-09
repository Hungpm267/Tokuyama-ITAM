"""Dọn master data: mã thiết bị, bỏ mã GA và mã phòng ban, loại nhân sự.

- `assets.pc_name` -> `assets.device_code`, bắt buộc, dùng cho mọi loại tài sản.
- Bỏ `assets.asset_code` (tem GA, không tài sản nào dùng) và CHECK "phải có một mã".
- Bỏ `departments.code` (chỉ giữ tên).
- Thêm `persons.person_type` (Nhân viên chính thức / Vendor / Công tác Nhật). Người chưa có mã
  được phân loại theo email người dùng cung cấp và nhận mã VND-NNN / JP-NNN; sau đó mã nhân
  viên thành bắt buộc.

CẢNH BÁO: xóa vĩnh viễn cột mã phòng ban, phải sao lưu trước. Code mới và migration phải lên
cùng lúc vì tên cột đã đổi.

Revision ID: 0007
Revises: 0006
"""

import re
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: Union[str, Sequence[str], None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

#: Người dùng phân loại ngày 09/11/2026 (theo email).
VENDOR_EMAILS = (
    "l.hoangduc.rr@tokuyamagr.com",
    "m.hoangthi.h7@tokuyamagr.com",
    "k.lenguyennhat.9x@tokuyamagr.com",
)
BUSINESS_TRIP_EMAILS = (
    "h.asada@tokuyama.com.vn",
    "h.sugimoto.ph@tokuyamagr.com",
    "a.takeda.sc@tokuyamagr.com",
)
PREFIX = {"VENDOR": "VND-", "BUSINESS_TRIP": "JP-"}

person_type = postgresql.ENUM("EMPLOYEE", "VENDOR", "BUSINESS_TRIP", name="person_type", create_type=False)


def _assign_codes(bind) -> None:
    rows = bind.execute(sa.text(
        "SELECT id, full_name, lower(coalesce(email, '')) FROM persons "
        "WHERE staff_code IS NULL ORDER BY is_deleted, full_name, id"
    )).all()
    used = {
        kind: [
            int(m.group(1))
            for (code,) in bind.execute(sa.text("SELECT staff_code FROM persons WHERE staff_code LIKE :p"), {"p": prefix + "%"})
            if (m := re.fullmatch(re.escape(prefix) + r"(\d+)", code))
        ]
        for kind, prefix in PREFIX.items()
    }
    for person_id, full_name, email in rows:
        kind = "BUSINESS_TRIP" if email in BUSINESS_TRIP_EMAILS else "VENDOR"
        number = max(used[kind], default=0) + 1
        used[kind].append(number)
        code = f"{PREFIX[kind]}{number:03d}"
        bind.execute(
            sa.text("UPDATE persons SET person_type = :t, staff_code = :c WHERE id = :i"),
            {"t": kind, "c": code, "i": person_id},
        )
        unlisted = "" if email in VENDOR_EMAILS + BUSINESS_TRIP_EMAILS else "  (không có trong danh sách, mặc định Vendor)"
        print(f"  {full_name}: {kind} {code}{unlisted}")


def upgrade() -> None:
    bind = op.get_bind()
    # Ô chỉ có khoảng trắng coi như trống, để không lọt qua các bước kiểm tra phía dưới.
    bind.execute(sa.text("UPDATE persons SET staff_code = NULL WHERE btrim(staff_code) = ''"))
    bind.execute(sa.text("UPDATE assets SET pc_name = NULL WHERE btrim(pc_name) = ''"))
    bind.execute(sa.text("UPDATE assets SET asset_code = NULL WHERE btrim(asset_code) = ''"))
    bad = bind.execute(sa.text(
        "SELECT count(*) FROM assets WHERE asset_code IS NOT NULL OR (pc_name IS NULL AND NOT is_deleted)"
    )).scalar()
    if bad:
        raise RuntimeError(
            f"{bad} tài sản còn mã GA hoặc tài sản đang dùng chưa có PC name. Hãy sửa tay trước khi chạy migration 0007."
        )
    # Bản ghi đã xóa mềm không có PC name (vd 20 dòng "PDF License" cũ): lấy serial làm mã thiết bị.
    bind.execute(sa.text(
        "UPDATE assets SET pc_name = coalesce(serial, 'DELETED-' || id) WHERE pc_name IS NULL AND is_deleted"
    ))

    # --- Tài sản ---
    op.execute("ALTER TABLE assets DROP CONSTRAINT ck_assets_has_some_identifier")
    op.drop_index("uq_alive_assets_asset_code", table_name="assets")
    op.drop_column("assets", "asset_code")
    op.alter_column("assets", "pc_name", new_column_name="device_code", nullable=False,
                    existing_type=sa.String(length=50))
    op.execute("ALTER INDEX uq_alive_assets_pc_name RENAME TO uq_alive_assets_device_code")

    # --- Phòng ban ---
    op.drop_index("uq_alive_departments_code", table_name="departments")
    op.drop_column("departments", "code")

    # --- Nhân sự ---
    person_type.create(bind, checkfirst=False)
    op.add_column("persons", sa.Column("person_type", person_type, server_default="EMPLOYEE", nullable=False))
    _assign_codes(bind)
    op.alter_column("persons", "staff_code", nullable=False, existing_type=sa.String(length=50))


def downgrade() -> None:
    raise NotImplementedError(
        "Migration 0007 đã xóa cột mã phòng ban và mã GA, không thể hạ phiên bản. Hãy phục hồi từ bản sao lưu."
    )
