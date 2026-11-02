"""Cho phép nhân sự không có mã nhân viên.

Một số người trong sheet Excel chưa có mã (người Nhật mới sang, nhân sự mới). Mã
bắt buộc khiến họ không có hồ sơ và không nhận bàn giao máy được. Mã có giá trị vẫn
phải duy nhất trong các bản ghi còn sống.

Revision ID: 0004
Revises: 0003
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, Sequence[str], None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index("uq_alive_persons_staff_code", table_name="persons")
    op.alter_column("persons", "staff_code", existing_type=sa.String(length=50), nullable=True)
    op.create_index(
        "uq_alive_persons_staff_code",
        "persons",
        ["staff_code"],
        unique=True,
        postgresql_where=sa.text("is_deleted = false AND staff_code IS NOT NULL"),
    )


def downgrade() -> None:
    # Hạ phiên bản sẽ thất bại nếu đã có nhân sự không có mã: phải điền mã trước.
    op.drop_index("uq_alive_persons_staff_code", table_name="persons")
    op.alter_column("persons", "staff_code", existing_type=sa.String(length=50), nullable=False)
    op.create_index(
        "uq_alive_persons_staff_code",
        "persons",
        ["staff_code"],
        unique=True,
        postgresql_where=sa.text("is_deleted = false"),
    )
