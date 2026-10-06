"""Khoá audit_logs ở tầng database: chỉ INSERT và SELECT.

BRD: "Không ai sửa được audit log, kể cả Admin."

Chỉ dựa vào tầng ứng dụng là không đủ. Người có chuỗi kết nối DB - chính là IT,
người cần bị kiểm soát nhất vì có toàn quyền - vẫn chạy được UPDATE bằng psql.
Trigger này chặn ở nơi mà không ứng dụng nào đi vòng qua được.

Revision ID: 0002
Revises: 0001
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0002"
down_revision: Union[str, Sequence[str], None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION itam_audit_immutable()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION
                'audit_logs chi cho phep INSERT va SELECT (thao tac bi chan: %)',
                TG_OP
            USING ERRCODE = 'check_violation';
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_audit_logs_no_update
        BEFORE UPDATE ON audit_logs
        FOR EACH ROW EXECUTE FUNCTION itam_audit_immutable();
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_audit_logs_no_delete
        BEFORE DELETE ON audit_logs
        FOR EACH ROW EXECUTE FUNCTION itam_audit_immutable();
        """
    )
    # TRUNCATE đi vòng qua trigger FOR EACH ROW, nên chặn riêng.
    op.execute(
        """
        CREATE TRIGGER trg_audit_logs_no_truncate
        BEFORE TRUNCATE ON audit_logs
        FOR EACH STATEMENT EXECUTE FUNCTION itam_audit_immutable();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_audit_logs_no_truncate ON audit_logs;")
    op.execute("DROP TRIGGER IF EXISTS trg_audit_logs_no_delete ON audit_logs;")
    op.execute("DROP TRIGGER IF EXISTS trg_audit_logs_no_update ON audit_logs;")
    op.execute("DROP FUNCTION IF EXISTS itam_audit_immutable();")
