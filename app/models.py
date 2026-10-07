"""Toàn bộ 23 bảng của hệ thống ITAM - Tokuyama Vietnam.

FILE NÀY LÀ NGUỒN SỰ THẬT DUY NHẤT CỦA SCHEMA.
Không tạo file model khác. Không sửa bảng bằng SQL tay. Mọi thay đổi đi qua
Alembic. Trước khi thêm/bớt một cột, đọc lại GEMINI.md mục "Bất biến".

Phân hệ:
  1. Hệ thống & phân quyền   users, roles, role_permissions, user_permission_overrides
  2. Danh mục dùng chung     departments, asset_categories, asset_tags, locations
  3. Nhân sự                 persons, person_secrets
  4. Tài sản                 assets, asset_tag_links, assignments
  5. License                 license_products, licenses, license_assignments
  6. Thẻ ra vào              access_cards, access_card_locations, card_loans
  7. Hợp đồng                contracts, contract_lines
  8. Danh bạ thoại           phones
  9. Truy vết                audit_logs
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
    CardStatus,
    CardType,
    DeliveryStatus,
    LicenseType,
    PersonStatus,
    PhoneDeviceType,
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


class UserPermissionOverride(Base):
    """Admin cấp thêm / thu hồi quyền lẻ cho một người, không đổi vai trò."""

    __tablename__ = "user_permission_overrides"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    module: Mapped[str] = mapped_column(String(40), nullable=False)
    action: Mapped[str] = mapped_column(String(10), nullable=False)
    granted: Mapped[bool] = mapped_column(Boolean, nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "module", "action"),
        CheckConstraint(
            "action IN ('view', 'add', 'change', 'delete')", name="action_allowed"
        ),
    )

    def __str__(self) -> str:
        status = "Allow" if self.granted else "Deny"
        return f"User #{self.user_id} - {self.module}:{self.action} ({status})"


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


class Location(BizBase):
    """Danh mục vị trí, dùng chung cho Phone List và Thẻ ra vào.

    Tên phòng chỉ nhập một lần ở đây. Mọi nơi khác chọn từ danh sách.
    Lỗi chính tả trong Excel cũ (Offce Room, Analysys Room) sửa khi seed.
    """

    __tablename__ = "locations"

    building: Mapped[str] = mapped_column(String(50), nullable=False)
    floor: Mapped[str] = mapped_column(String(50), nullable=False)
    room_en: Mapped[str] = mapped_column(String(100), nullable=False)
    room_ja: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_access_controlled: Mapped[bool] = mapped_column(
        Boolean, server_default=text("false"), nullable=False
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = biz_args(
        alive_unique("locations", "building", "floor", "room_en")
    )

    def __str__(self) -> str:
        parts = [p for p in (self.building, self.floor, self.room_en) if p]
        return " - ".join(parts) if parts else f"Location #{self.id}"


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

    staff_code: Mapped[str] = mapped_column(String(50), nullable=False)
    user_login_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
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
        alive_unique("persons", "staff_code"),
        alive_unique("persons", "user_login_id", extra="user_login_id IS NOT NULL"),
        alive_unique("persons", "email", extra="email IS NOT NULL"),
        Index("ix_persons_full_name", "full_name"),
    )

    def __str__(self) -> str:
        return f"{self.full_name} ({self.staff_code})"


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
      vendor_code - mã KDDI gán khi giao, vd TKY-PC0001
    """

    __tablename__ = "assets"

    asset_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    vendor_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    category_id: Mapped[int] = mapped_column(
        ForeignKey("asset_categories.id", ondelete="RESTRICT"), nullable=False
    )
    contract_line_id: Mapped[int | None] = mapped_column(
        ForeignKey("contract_lines.id", ondelete="RESTRICT"), nullable=True
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
    contract_line: Mapped[ContractLine | None] = relationship(
        back_populates="assets"
    )
    assignments: Mapped[list[Assignment]] = relationship(back_populates="asset")

    __table_args__ = biz_args(
        alive_unique("assets", "asset_code", extra="asset_code IS NOT NULL"),
        alive_unique("assets", "vendor_code", extra="vendor_code IS NOT NULL"),
        alive_unique("assets", "serial", extra="serial IS NOT NULL"),
        Index("ix_assets_hwid", "hwid"),
        Index("ix_assets_mac_ethernet", "mac_ethernet"),
        Index("ix_assets_mac_wifi", "mac_wifi"),
        CheckConstraint(
            "asset_code IS NOT NULL OR vendor_code IS NOT NULL OR serial IS NOT NULL",
            name="has_some_identifier",
        ),
    )

    def __str__(self) -> str:
        code = self.asset_code or self.vendor_code or self.serial or f"Asset #{self.id}"
        return f"{code} ({self.model})" if self.model else str(code)


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
# 5. LICENSE
# =============================================================================


class LicenseProduct(BizBase):
    """Windows, Office LTSC 2024 CSP, IJCAD, Visio, PDF, Trend Micro, MS365."""

    __tablename__ = "license_products"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    vendor: Mapped[str | None] = mapped_column(String(100), nullable=True)
    license_type: Mapped[LicenseType | None] = mapped_column(
        _enum(LicenseType, "license_type"), nullable=True
    )

    __table_args__ = biz_args(alive_unique("license_products", "name"))

    def __str__(self) -> str:
        return self.name


class License(BizBase):
    """Một gói license đã mua."""

    __tablename__ = "licenses"

    product_id: Mapped[int] = mapped_column(
        ForeignKey("license_products.id", ondelete="RESTRICT"), nullable=False
    )
    license_key_enc: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    key_version: Mapped[int] = mapped_column(
        SmallInteger, server_default=text("1"), nullable=False
    )
    seats: Mapped[int] = mapped_column(Integer, nullable=False)
    start_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    expiry_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    contract_id: Mapped[int | None] = mapped_column(
        ForeignKey("contracts.id", ondelete="RESTRICT"), nullable=True
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    product: Mapped[LicenseProduct] = relationship()
    assignments: Mapped[list[LicenseAssignment]] = relationship(
        back_populates="license"
    )

    __table_args__ = biz_args(
        CheckConstraint("seats > 0", name="seats_positive"),
        CheckConstraint(
            "expiry_date IS NULL OR start_date IS NULL OR expiry_date >= start_date",
            name="expiry_after_start",
        ),
    )

    def __str__(self) -> str:
        prod = self.product.name if self.product else "License"
        return f"{prod} ({self.seats} seats)"


class LicenseAssignment(BizBase):
    """Gán license cho MỘT máy hoặc MỘT người.

    expiry_date ở đây là hạn riêng của lần gán, ghi đè hạn của gói. Cần cho
    Trend Micro vì sheet Excel hiện tại ghi expire date theo từng PC.
    """

    __tablename__ = "license_assignments"

    license_id: Mapped[int] = mapped_column(
        ForeignKey("licenses.id", ondelete="RESTRICT"), nullable=False
    )
    asset_id: Mapped[int | None] = mapped_column(
        ForeignKey("assets.id", ondelete="RESTRICT"), nullable=True
    )
    person_id: Mapped[int | None] = mapped_column(
        ForeignKey("persons.id", ondelete="RESTRICT"), nullable=True
    )
    assigned_at: Mapped[dt.date] = mapped_column(Date, nullable=False)
    expiry_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    removed_at: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    license: Mapped[License] = relationship(back_populates="assignments")

    __table_args__ = biz_args(
        CheckConstraint(
            "asset_id IS NOT NULL OR person_id IS NOT NULL",
            name="target_required",
        ),
        closes_after_opens("assigned_at", "removed_at", "removed_after_assigned"),
        one_open_per(
            "license_assignments",
            "license_id",
            "asset_id",
            close_col="removed_at",
            extra="asset_id IS NOT NULL",
        ),
        one_open_per(
            "license_assignments",
            "license_id",
            "person_id",
            close_col="removed_at",
            extra="person_id IS NOT NULL",
        ),
    )

    def __str__(self) -> str:
        return f"LicenseAssignment #{self.id}"


# =============================================================================
# 6. THẺ RA VÀO
# =============================================================================


class AccessCard(BizBase):
    __tablename__ = "access_cards"

    card_no: Mapped[str] = mapped_column(String(50), nullable=False)
    card_type: Mapped[CardType] = mapped_column(
        _enum(CardType, "card_type"),
        server_default=text("'CONTRACTOR'"),
        nullable=False,
    )
    status: Mapped[CardStatus] = mapped_column(
        _enum(CardStatus, "card_status"),
        server_default=text("'IN_STOCK'"),
        nullable=False,
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    loans: Mapped[list[CardLoan]] = relationship(back_populates="card")

    __table_args__ = biz_args(alive_unique("access_cards", "card_no"))

    def __str__(self) -> str:
        card_type_val = (
            self.card_type.value
            if hasattr(self.card_type, "value")
            else str(self.card_type)
        )
        return f"{self.card_no} ({card_type_val})"


class AccessCardLocation(LinkBase):
    """Thẻ nào vào được phòng nào.

    Câu tiếng Nhật kiểu "Document Room, Server Room, Master Room 以外の部屋"
    phải được QUY ĐỔI thành danh sách phòng cụ thể khi nhập liệu. Không lưu câu.
    """

    __tablename__ = "access_card_locations"

    card_id: Mapped[int] = mapped_column(
        ForeignKey("access_cards.id", ondelete="CASCADE"), primary_key=True
    )
    location_id: Mapped[int] = mapped_column(
        ForeignKey("locations.id", ondelete="RESTRICT"), primary_key=True
    )


class CardLoan(BizBase):
    """Một lần cho mượn thẻ. Người mượn là nhân viên HOẶC người bên ngoài."""

    __tablename__ = "card_loans"

    card_id: Mapped[int] = mapped_column(
        ForeignKey("access_cards.id", ondelete="RESTRICT"), nullable=False
    )
    person_id: Mapped[int | None] = mapped_column(
        ForeignKey("persons.id", ondelete="RESTRICT"), nullable=True
    )
    external_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    external_company: Mapped[str | None] = mapped_column(String(150), nullable=True)
    purpose: Mapped[str | None] = mapped_column(Text, nullable=True)
    borrowed_at: Mapped[dt.date] = mapped_column(Date, nullable=False)
    expected_return_at: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    returned_at: Mapped[dt.date | None] = mapped_column(Date, nullable=True)

    card: Mapped[AccessCard] = relationship(back_populates="loans")

    __table_args__ = biz_args(
        CheckConstraint(
            "person_id IS NOT NULL"
            " OR (external_name IS NOT NULL AND length(btrim(external_name)) > 0)",
            name="borrower_required",
        ),
        closes_after_opens("borrowed_at", "returned_at", "returned_after_borrowed"),
        closes_after_opens(
            "borrowed_at", "expected_return_at", "expected_after_borrowed"
        ),
        one_open_per("card_loans", "card_id", close_col="returned_at"),
    )

    def __str__(self) -> str:
        return f"Loan #{self.id}"


# =============================================================================
# 7. HỢP ĐỒNG
# =============================================================================


class Contract(BizBase):
    __tablename__ = "contracts"

    code: Mapped[str] = mapped_column(String(50), nullable=False)
    vendor_name: Mapped[str | None] = mapped_column(
        String(100), server_default=text("'KDDI Vietnam'"), nullable=True
    )
    signed_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    delivery_status: Mapped[DeliveryStatus] = mapped_column(
        _enum(DeliveryStatus, "delivery_status"),
        server_default=text("'PENDING'"),
        nullable=False,
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    lines: Mapped[list[ContractLine]] = relationship(back_populates="contract")

    __table_args__ = biz_args(alive_unique("contracts", "code"))

    def __str__(self) -> str:
        vendor = f" - {self.vendor_name}" if self.vendor_name else ""
        return f"{self.code}{vendor}"


class ContractLine(BizBase):
    """Một dòng hàng trong hợp đồng.

    KHÔNG có delivered_qty hay remaining_qty. Số đã nhận được ĐẾM từ
    assets.contract_line_id. Đây là điểm sửa quan trọng nhất so với sheet
    "PC_Qty summary" - cột gõ tay đó chính là nguồn sai lệch.
    """

    __tablename__ = "contract_lines"

    contract_id: Mapped[int] = mapped_column(
        ForeignKey("contracts.id", ondelete="RESTRICT"), nullable=False
    )
    item_type: Mapped[str] = mapped_column(String(100), nullable=False)
    spec: Mapped[str | None] = mapped_column(Text, nullable=True)
    qty_ordered: Mapped[int] = mapped_column(Integer, nullable=False)

    contract: Mapped[Contract] = relationship(back_populates="lines")
    assets: Mapped[list[Asset]] = relationship(back_populates="contract_line")

    __table_args__ = biz_args(
        CheckConstraint("qty_ordered > 0", name="qty_positive")
    )

    def __str__(self) -> str:
        return f"{self.item_type} (x{self.qty_ordered})"


# =============================================================================
# 8. DANH BẠ THOẠI
# =============================================================================


class Phone(BizBase):
    __tablename__ = "phones"

    device_name: Mapped[str] = mapped_column(String(50), nullable=False)
    device_type: Mapped[PhoneDeviceType] = mapped_column(
        _enum(PhoneDeviceType, "phone_device_type"), nullable=False
    )
    extension_number: Mapped[str | None] = mapped_column(String(10), nullable=True)
    location_id: Mapped[int | None] = mapped_column(
        ForeignKey("locations.id", ondelete="RESTRICT"), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, server_default=text("true"), nullable=False
    )
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)

    location: Mapped[Location | None] = relationship()

    __table_args__ = biz_args(
        alive_unique("phones", "device_name"),
        alive_unique(
            "phones", "extension_number", extra="extension_number IS NOT NULL"
        ),
        CheckConstraint(
            "extension_number IS NULL OR extension_number <> 'N/A'",
            name="no_na_literal",
        ),
    )

    def __str__(self) -> str:
        ext = f" (Ext: {self.extension_number})" if self.extension_number else ""
        return f"{self.device_name}{ext}"


# =============================================================================
# 9. TRUY VẾT
# =============================================================================


class AuditLog(Base):
    """Nhật ký chỉ-thêm. Trigger DB chặn mọi UPDATE và DELETE, kể cả của Admin.

    before_after KHÔNG BAO GIỜ được chứa giá trị của *_enc, password_hash hay
    license key. Lớp ghi audit phải lọc theo danh sách REDACTED_FIELDS.
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

    __table_args__ = (
        Index("ix_audit_logs_table_record", "table_name", "record_id"),
        Index("ix_audit_logs_created_at", "created_at"),
        Index("ix_audit_logs_user_action", "user_id", "action"),
    )

    def __str__(self) -> str:
        return f"Audit #{self.id} ({self.action.value} {self.table_name})"


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
