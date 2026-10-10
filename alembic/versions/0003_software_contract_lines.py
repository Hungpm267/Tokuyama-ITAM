"""Hạng mục hợp đồng loại Phần mềm.

Trước đây số "đã nhận" của một hạng mục chỉ đếm được từ thiết bị
(`assets.contract_line_id`), nên hợp đồng mua phần mềm không bao giờ nhận đủ.

- `contract_lines.item_kind`: hạng mục mua phần cứng hay phần mềm. Hạng mục cũ
  mặc định là HARDWARE nên dữ liệu hiện có không đổi nghĩa.
- `licenses.contract_line_id`: gói license nhận về cho hạng mục nào. Số đã nhận
  của hạng mục phần mềm = SUM(seats) của các gói còn sống, vẫn KHÔNG có cột gõ tay.

Revision ID: 0003
Revises: 0002
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, Sequence[str], None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

item_kind = sa.Enum("HARDWARE", "SOFTWARE", name="contract_item_kind")


def upgrade() -> None:
    item_kind.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "contract_lines",
        sa.Column("item_kind", item_kind, server_default=sa.text("'HARDWARE'"), nullable=False),
    )
    op.add_column("licenses", sa.Column("contract_line_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        op.f("fk_licenses_contract_line_id"),
        "licenses",
        "contract_lines",
        ["contract_line_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(op.f("ix_licenses_contract_line_id"), "licenses", ["contract_line_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_licenses_contract_line_id"), table_name="licenses")
    op.drop_constraint(op.f("fk_licenses_contract_line_id"), "licenses", type_="foreignkey")
    op.drop_column("licenses", "contract_line_id")
    op.drop_column("contract_lines", "item_kind")
    item_kind.drop(op.get_bind(), checkfirst=True)
