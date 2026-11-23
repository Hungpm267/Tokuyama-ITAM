"""Đổi tiền tố mã thiết bị TKY-PC sang TVC-EC, giữ nguyên số (kể cả máy đã xóa mềm).

Revision ID: 0008
Revises: 0007
"""

from __future__ import annotations

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

# Nhật ký truy vết cũ vẫn ghi mã TKY-PC: audit_logs bất biến, không sửa.
UPGRADE_SQL = (
    "UPDATE assets SET device_code = 'TVC-EC' || substr(device_code, 7) "
    "WHERE upper(device_code) LIKE 'TKY-PC%'"
)
DOWNGRADE_SQL = (
    "UPDATE assets SET device_code = 'TKY-PC' || substr(device_code, 7) "
    "WHERE upper(device_code) LIKE 'TVC-EC%'"
)


def upgrade() -> None:
    op.execute(UPGRADE_SQL)


def downgrade() -> None:
    op.execute(DOWNGRADE_SQL)
