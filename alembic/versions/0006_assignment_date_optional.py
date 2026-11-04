"""Cho phép lượt bàn giao không có ngày giao.

Nhiều lượt bàn giao nhập từ file Excel không ai còn biết ngày thật. Trống nghĩa là
máy vẫn ở chỗ người đó, chỉ không rõ ngày giao.

Revision ID: 0006
Revises: 0005
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: Union[str, Sequence[str], None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("assignments", "borrowed_at", existing_type=sa.Date(), nullable=True)


def downgrade() -> None:
    # Hạ phiên bản sẽ thất bại nếu đã có lượt bàn giao không có ngày: phải điền ngày trước.
    op.alter_column("assignments", "borrowed_at", existing_type=sa.Date(), nullable=False)
