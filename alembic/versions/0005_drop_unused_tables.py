"""Thu hẹp schema về laptop và nhân sự: bỏ 11 bảng, đặt lại tên hai cột, bổ sung một khóa ngoại.

App không còn màn hình nào cho hợp đồng, license, thẻ, danh bạ thoại và vị trí, nên
các bảng đó bị xóa hẳn. `user_permission_overrides` cũng bỏ vì phân quyền chỉ còn hai
mức. Hai cột đổi sang tên nghiệp vụ: `assets.vendor_code` -> `pc_name`,
`persons.user_login_id` -> `user_id`.

Migration 0001 khai báo `users.role_id` với use_alter nên `create_table` bỏ qua khóa
ngoại này. Database dựng bằng con đường khác có thể đã có sẵn, vì vậy phải kiểm tra trước.

CẢNH BÁO: migration này xóa dữ liệu vĩnh viễn và không có đường lùi, phải sao lưu
database trước khi chạy. Code mới và migration phải lên cùng lúc vì tên cột đã đổi.

Revision ID: 0005
Revises: 0004
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0005"
down_revision: Union[str, Sequence[str], None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

#: Xếp theo khóa ngoại: bảng con trước, bảng cha sau.
DROPPED_TABLES = (
    "phones",
    "card_loans",
    "access_card_locations",
    "access_cards",
    "license_assignments",
    "licenses",
    "license_products",
    "contract_lines",
    "contracts",
    "locations",
    "user_permission_overrides",
)
DROPPED_ENUMS = (
    "phone_device_type",
    "card_status",
    "card_type",
    "license_type",
    "contract_item_kind",
    "delivery_status",
)


def upgrade() -> None:
    op.drop_column("assets", "contract_line_id")
    for table in DROPPED_TABLES:
        op.drop_table(table)
    for enum in DROPPED_ENUMS:
        op.execute(f"DROP TYPE {enum}")
    op.execute(
        "DELETE FROM role_permissions WHERE module IN ('licenses', 'cards', 'contracts', 'phones')"
    )

    # PostgreSQL tự cập nhật điều kiện của index và CHECK theo tên cột mới.
    op.alter_column("assets", "vendor_code", new_column_name="pc_name")
    op.execute("ALTER INDEX uq_alive_assets_vendor_code RENAME TO uq_alive_assets_pc_name")
    op.alter_column("persons", "user_login_id", new_column_name="user_id")
    op.execute("ALTER INDEX uq_alive_persons_user_login_id RENAME TO uq_alive_persons_user_id")

    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conrelid = 'users'::regclass AND contype = 'f'
                  AND conkey = ARRAY[(
                      SELECT attnum FROM pg_attribute
                      WHERE attrelid = 'users'::regclass AND attname = 'role_id'
                  )]
            ) THEN
                ALTER TABLE users ADD CONSTRAINT fk_users_role_id
                    FOREIGN KEY (role_id) REFERENCES roles (id) ON DELETE RESTRICT;
            END IF;
        END $$
        """
    )


def downgrade() -> None:
    raise NotImplementedError(
        "Migration 0005 đã xóa bảng và dữ liệu, không thể hạ phiên bản. Hãy phục hồi từ bản sao lưu."
    )
