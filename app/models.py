"""Toàn bộ 12 bảng của hệ thống ITAM - Tokuyama Vietnam.

FILE NÀY LÀ NGUỒN SỰ THẬT DUY NHẤT CỦA SCHEMA.
Không tạo file model khác. Không sửa bảng bằng SQL tay. Mọi thay đổi đi qua
Alembic. Trước khi thêm/bớt một cột, đọc lại GEMINI.md mục "Bất biến".

Phân hệ:
  1. Hệ thống & phân quyền   users, roles, role_permissions
  2. Danh mục dùng chung     departments, asset_categories, asset_tags
  3. Nhân sự                 persons, person_secrets
  4. Tài sản                 assets, asset_tag_links, assignments
  5. Truy vết                audit_logs
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import (
    Base,
    BizBase,
    LinkBase,
    alive_unique,
    biz_args,
    closes_after_opens,
    one_open_per,
)
from app.enums import (
    AssetStatus,
    AuditAction,
    PersonStatus,
)


def _enum(py_enum, name: str) -> SAEnum:
    """ENUM native PostgreSQL, lưu theo .value chứ không theo .name."""
    return SAEnum(
        py_enum,
        name=name,
        native_enum=True,
        values_callable=lambda e: [m.value for m in e],
    )


# =============================================================================
# 1. HỆ THỐNG & PHÂN QUYỀN
# =============================================================================


class User(BizBase):
    """Tài khoản đăng nhập hệ thống. Đợt 1 chỉ có 5 tài khoản."""

    __tablename__ = "users"

    username: Mapped[str] = mapped_column(String(50), nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    # use_alter: users.role_id -> roles.id và roles.created_by -> users.id tạo
    # thành vòng. Tách FK này ra một lệnh ALTER chạy sau khi cả hai bảng đã có,
    # nếu không CREATE TABLE sẽ thất bại vì không biết tạo bảng nào trước.
    role_id: Mapped[int] = mapped_column(
        ForeignKey("roles.id", ondelete="RESTRICT", use_alter=True), nullable=False
    )
    preferred_lang: Mapped[str] = mapped_column(
        String(5), server_default=text("'en'"), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, server_default=text("true"), nullable=False
    )
    last_login_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # foreign_keys bắt buộc: users.role_id -> roles VÀ roles.created_by -> users,
    # nên SQLAlchemy không tự đoán được nên đi theo đường nào.
    role: Mapped[Role] = relationship(
        back_populates="users", foreign_keys="User.role_id"
    )

    __table_args__ = biz_args(
        alive_unique("users", "username"),
        CheckConstraint(
            "preferred_lang IN ('en', 'ja', 'vi')", name="lang_allowed"
        ),
    )

    def __str__(self) -> str:
        return f"{self.display_name} ({self.username})"


class Role(BizBase):
    __tablename__ = "roles"

    code: Mapped[str] = mapped_column(String(30), nullable=False)
    name_en: Mapped[str] = mapped_column(String(100), nullable=False)
    name_ja: Mapped[str | None] = mapped_column(String(100), nullable=True)

    users: Mapped[list[User]] = relationship(
        back_populates="role", foreign_keys="User.role_id"
    )
    permissions: Mapped[list[RolePermission]] = relationship(
        back_populates="role", cascade="all, delete-orphan"
    )

    __table_args__ = biz_args(alive_unique("roles", "code"))

    def __str__(self) -> str:
        return f"{self.name_en} ({self.code})"


class RolePermission(Base):
    """Quyền mặc định theo vai trò. Bảng nối: không audit, không xoá mềm."""

    __tablename__ = "role_permissions"

    id: Mapped[int] = mapped_column(primary_key=True)
    role_id: Mapped[int] = mapped_column(
        ForeignKey("roles.id", ondelete="CASCADE"), nullable=False
    )
    module: Mapped[str] = mapped_column(String(40), nullable=False)
    action: Mapped[str] = mapped_column(String(10), nullable=False)

    role: Mapped[Role] = relationship(back_populates="permissions")

    __table_args__ = (
        UniqueConstraint("role_id", "module", "action"),
        CheckConstraint(
            "action IN ('view', 'add', 'change', 'delete')", name="action_allowed"
        ),
    )

    def __str__(self) -> str:
        return f"{self.module}:{self.action}"


# =============================================================================
# 2. DANH MỤC DÙNG CHUNG
# =============================================================================


class Department(BizBase):
    __tablename__ = "departments"

    code: Mapped[str | None] = mapped_column(String(30), nullable=True)
    name_en: Mapped[str] = mapped_column(String(100), nullable=False)
    name_ja: Mapped[str | None] = mapped_column(String(100), nullable=True)

    __table_args__ = biz_args(
        alive_unique("departments", "code", extra="code IS NOT NULL"),
        alive_unique("departments", "name_en"),
    )

    def __str__(self) -> str:
        return f"{self.name_en} ({self.code})" if self.code else self.name_en


class AssetCategory(BizBase):
    """Laptop, Monitor, Handy Terminal, Mouse..."""

    __tablename__ = "asset_categories"

    name_en: Mapped[str] = mapped_column(String(100), nullable=False)
    name_ja: Mapped[str | None] = mapped_column(String(100), nullable=True)

    __table_args__ = biz_args(alive_unique("asset_categories", "name_en"))

    def __str__(self) -> str:
        return self.name_en


class AssetTag(BizBase):
    """Nhãn tự định nghĩa cho tài sản: ZSCALER, MES...

    Thay cho các cột boolean has_zscaler / is_mes_machine. Thêm nhãn mới =
    INSERT một dòng, KHÔNG chạy migration. Đây là nguyên tắc cốt lõi của BRD:
    thuộc tính mở rộng được thì không bao giờ là cột.
    """

    __tablename__ = "asset_tags"

    code: Mapped[str] = mapped_column(String(30), nullable=False)
    name_en: Mapped[str] = mapped_column(String(100), nullable=False)
    name_ja: Mapped[str | None] = mapped_column(String(100), nullable=True)
    color: Mapped[str | None] = mapped_column(String(7), nullable=True)

    __table_args__ = biz_args(alive_unique("asset_tags", "code"))

    def __str__(self) -> str:
        return f"{self.name_en} ({self.code})"


# =============================================================================
# 3. NHÂN SỰ
# =============================================================================


class Person(BizBase):
    """Nhân viên. Bảng trung tâm thứ nhất.

    KHÔNG chứa mật khẩu - xem PersonSecret. Đây là chủ ý thiết kế: một câu
    SELECT * trên bảng này, hay một lần export CSV, không bao giờ kéo theo
    dữ liệu nhạy cảm.
    """

    __tablename__ = "persons"

    #: Để trống được: người mới có thể chưa được cấp mã.
    staff_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    user_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    full_name: Mapped[str] = mapped_column(String(100), nullable=False)
    department_id: Mapped[int | None] = mapped_column(
        ForeignKey("departments.id", ondelete="RESTRICT"), nullable=True
    )
    email: Mapped[str | None] = mapped_column(String(150), nullable=True)
    status: Mapped[PersonStatus] = mapped_column(
        _enum(PersonStatus, "person_status"),
        server_default=text("'ACTIVE'"),
        nullable=False,
    )
    start_working_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    department: Mapped[Department | None] = relationship()
    secret: Mapped[PersonSecret | None] = relationship(
        back_populates="person", uselist=False, cascade="all, delete-orphan"
    )
    assignments: Mapped[list[Assignment]] = relationship(back_populates="person")

    __table_args__ = biz_args(
        alive_unique("persons", "staff_code", extra="staff_code IS NOT NULL"),
        alive_unique("persons", "user_id", extra="user_id IS NOT NULL"),
        alive_unique("persons", "email", extra="email IS NOT NULL"),
        Index("ix_persons_full_name", "full_name"),
    )

    def __str__(self) -> str:
        return f"{self.full_name} ({self.staff_code})" if self.staff_code else self.full_name


class PersonSecret(Base):
    """Mật khẩu PC / email của nhân viên, đã mã hoá AES-256-GCM.

    CẤM TUYỆT ĐỐI:
      - Đưa cột *_enc vào bất kỳ response, template, log, CSV export nào.
      - Giải mã ở nơi khác ngoài app/core/secrets.py.
      - Thêm cột plaintext cho mật khẩu.
    Cột *_note là ghi chú KHÔNG bí mật (vd "mật khẩu cho máy MES") nên để thường
    và tìm kiếm được.
    """

    __tablename__ = "person_secrets"

    person_id: Mapped[int] = mapped_column(
        ForeignKey("persons.id", ondelete="CASCADE"), primary_key=True
    )
    pc_password_enc: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    pc_password_note: Mapped[str | None] = mapped_column(String(200), nullable=True)
    email_password_enc: Mapped[bytes | None] = mapped_column(
        LargeBinary, nullable=True
    )
    email_password_note: Mapped[str | None] = mapped_column(String(200), nullable=True)
    key_version: Mapped[int] = mapped_column(
        SmallInteger, server_default=text("1"), nullable=False
    )
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    updated_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )

    person: Mapped[Person] = relationship(back_populates="secret")


# =============================================================================
# 4. TÀI SẢN
# =============================================================================


class Asset(BizBase):
    """Một thiết bị vật lý. Bảng trung tâm thứ hai.

    Hai mã song song, cả hai đều có thể trống:
      asset_code  - mã tem GA tự dán, vd TVC-E00027
      pc_name     - tên máy KDDI gán khi giao, vd TKY-PC0001
    """

    __tablename__ = "assets"

    asset_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    pc_name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    category_id: Mapped[int] = mapped_column(
        ForeignKey("asset_categories.id", ondelete="RESTRICT"), nullable=False
    )
    model: Mapped[str | None] = mapped_column(String(150), nullable=True)
    form_factor: Mapped[str | None] = mapped_column(String(30), nullable=True)
    serial: Mapped[str | None] = mapped_column(String(100), nullable=True)
    hwid: Mapped[str | None] = mapped_column(String(100), nullable=True)
    mac_ethernet: Mapped[str | None] = mapped_column(String(20), nullable=True)
    mac_wifi: Mapped[str | None] = mapped_column(String(20), nullable=True)
    status: Mapped[AssetStatus] = mapped_column(
        _enum(AssetStatus, "asset_status"),
        server_default=text("'IN_STOCK'"),
        nullable=False,
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    category: Mapped[AssetCategory] = relationship()
    assignments: Mapped[list[Assignment]] = relationship(back_populates="asset")

    __table_args__ = biz_args(
        alive_unique("assets", "asset_code", extra="asset_code IS NOT NULL"),
        alive_unique("assets", "pc_name", extra="pc_name IS NOT NULL"),
        alive_unique("assets", "serial", extra="serial IS NOT NULL"),
        Index("ix_assets_hwid", "hwid"),
        Index("ix_assets_mac_ethernet", "mac_ethernet"),
        Index("ix_assets_mac_wifi", "mac_wifi"),
        CheckConstraint(
            "asset_code IS NOT NULL OR pc_name IS NOT NULL OR serial IS NOT NULL",
            name="has_some_identifier",
        ),
    )

    def __str__(self) -> str:
        code = self.asset_code or self.pc_name or self.serial or f"Asset #{self.id}"
        return f"{code} ({self.model})" if self.model else str(code)

    @property
    def current_holder(self) -> str | None:
        try:
            for asgn in self.assignments:
                if asgn.returned_at is None and asgn.person:
                    return str(asgn.person)
        except Exception:
            return None
        return None


class AssetTagLink(LinkBase):
    __tablename__ = "asset_tag_links"

    asset_id: Mapped[int] = mapped_column(
        ForeignKey("assets.id", ondelete="CASCADE"), primary_key=True
    )
    tag_id: Mapped[int] = mapped_column(
        ForeignKey("asset_tags.id", ondelete="RESTRICT"), primary_key=True
    )


class Assignment(BizBase):
    """Một lần cho mượn thiết bị. KHÔNG xoá, chỉ đóng bằng returned_at."""

    __tablename__ = "assignments"

    asset_id: Mapped[int] = mapped_column(
        ForeignKey("assets.id", ondelete="RESTRICT"), nullable=False
    )
    person_id: Mapped[int] = mapped_column(
        ForeignKey("persons.id", ondelete="RESTRICT"), nullable=False
    )
    borrowed_at: Mapped[dt.date] = mapped_column(Date, nullable=False)
    returned_at: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    asset: Mapped[Asset] = relationship(back_populates="assignments")
    person: Mapped[Person] = relationship(back_populates="assignments")

    __table_args__ = biz_args(
        one_open_per("assignments", "asset_id", close_col="returned_at"),
        closes_after_opens("borrowed_at", "returned_at", "returned_after_borrowed"),
    )

    def __str__(self) -> str:
        return f"Assignment #{self.id}"


# =============================================================================
# 5. TRUY VẾT
# =============================================================================


class AuditLog(Base):
    """Nhật ký chỉ-thêm. Trigger DB chặn mọi UPDATE và DELETE, kể cả của Admin.

    before_after KHÔNG BAO GIỜ được chứa giá trị của *_enc hay password_hash.
    Lớp ghi audit phải lọc theo danh sách REDACTED_FIELDS.
    """

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    table_name: Mapped[str] = mapped_column(String(50), nullable=False)
    record_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    action: Mapped[AuditAction] = mapped_column(
        _enum(AuditAction, "audit_action"), nullable=False
    )
    before_after: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(INET, nullable=True)

    user: Mapped[User | None] = relationship()

    __table_args__ = (
        Index("ix_audit_logs_table_record", "table_name", "record_id"),
        Index("ix_audit_logs_created_at", "created_at"),
        Index("ix_audit_logs_user_action", "user_id", "action"),
    )

    def __str__(self) -> str:
        return f"Audit #{self.id} ({self.action.value} {self.table_name})"

    @property
    def summary(self) -> str:
        if not self.before_after:
            if self.action == AuditAction.LOGIN:
                return "Đăng nhập thành công"
            return "-"
        extra = self.before_after.get("extra") or {}
        # Dòng RESTORE lưu lại lý do xóa cũ trong `before`; đừng trình bày nó như một lần xóa.
        if self.action == AuditAction.RESTORE:
            return "Khôi phục bản ghi từ thùng rác"
        if "delete_reason" in extra:
            return f"Lý do xóa: {extra['delete_reason']}"
        if "reason" in extra:
            return f"Lý do: {extra['reason']}"

        before = self.before_after.get("before") or {}
        if before.get("delete_reason"):
            return f"Lý do xóa: {before['delete_reason']}"

        if self.action == AuditAction.LOGIN:
            return "Đăng nhập thành công"
        if self.action == AuditAction.LOGIN_FAIL:
            return f"Đăng nhập thất bại ({extra.get('username', '')})"
        if self.action == AuditAction.REVEAL:
            return f"Xem mật khẩu: {extra.get('revealed_field') or extra.get('field', '')}"

        after = self.before_after.get("after") or {}
        if self.action == AuditAction.UPDATE and before and after:
            changed = [
                k for k in after
                if k in before and before[k] != after[k] and k not in ("updated_at", "updated_by")
            ]
            if changed:
                return f"Sửa: {', '.join(changed[:3])}"
        if self.action == AuditAction.CREATE:
            return "Tạo mới bản ghi"
        if self.action == AuditAction.DELETE:
            return "Xóa bản ghi"

        return "-"


#: Tên cột không bao giờ được xuất hiện trong audit log, API response,
#: template, CSV export hay dòng log nào.
REDACTED_FIELDS = frozenset(
    {
        "pc_password_enc",
        "email_password_enc",
        "license_key_enc",
        "password_hash",
    }
)
