"""Base declarative, mixin và helper ràng buộc.

ĐỌC TRƯỚC KHI SỬA: các helper ở đây mã hoá những quyết định trong BRD mục
"Quy tắc toàn vẹn bắt buộc có trong DB". Đừng thay `alive_unique()` bằng
`UniqueConstraint` - xem docstring của nó để biết tại sao.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    MetaData,
    String,
    create_engine,
    func,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column, sessionmaker
from app.config import settings

# Quy ước đặt tên ràng buộc. Bắt buộc có, nếu không Alembic sẽ sinh ra tên
# ngẫu nhiên và migration sau này không drop được constraint cũ.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def alive_unique(table: str, *columns: str, extra: str | None = None) -> Index:
    """Ràng buộc duy nhất CHỈ áp dụng cho bản ghi chưa xoá mềm.

    Vì sao không dùng UniqueConstraint: khi xoá mềm một tài sản có serial 'ABC'
    rồi nhập lại đúng serial đó, UniqueConstraint thường sẽ chặn. Partial unique
    index bỏ qua bản ghi đã xoá nên nhập lại được.

    `extra` thêm điều kiện, ví dụ 'serial IS NOT NULL' để nhiều bản ghi cùng
    để trống serial không đụng nhau (NULL trong PostgreSQL không bằng NULL,
    nhưng ghi rõ vẫn tốt hơn cho người đọc và cho query planner).
    """
    where = "is_deleted = false"
    if extra:
        where = f"{where} AND {extra}"
    name = "uq_alive_" + table + "_" + "_".join(columns)
    return Index(name, *columns, unique=True, postgresql_where=text(where))


def one_open_per(table: str, *columns: str, close_col: str, extra: str | None = None) -> Index:
    """Chỉ cho phép MỘT bản ghi đang mở tại một thời điểm.

    Đây là ràng buộc mà `UNIQUE (asset_id, returned_at)` KHÔNG làm được:
    trong PostgreSQL `NULL != NULL`, nên UniqueConstraint đó cho phép tạo vô số
    dòng cùng asset_id với returned_at = NULL. Bắt buộc dùng partial index.
    """
    where = f"{close_col} IS NULL AND is_deleted = false"
    if extra:
        where = f"{where} AND {extra}"
    name = "uq_open_" + table + "_" + "_".join(columns)
    return Index(name, *columns, unique=True, postgresql_where=text(where))


def closes_after_opens(opened: str, closed: str, label: str) -> CheckConstraint:
    """Ngày đóng không được trước ngày mở."""
    return CheckConstraint(
        f"{closed} IS NULL OR {closed} >= {opened}", name=label
    )


def soft_delete_coherent() -> CheckConstraint:
    """Ba cột xoá mềm phải nhất quán với nhau.

    Chặn trường hợp `is_deleted = true` mà không có lý do xoá - BRD bắt buộc
    nhập lý do, và nếu chỉ kiểm tra ở tầng ứng dụng thì một câu UPDATE chạy tay
    lúc gấp sẽ phá vỡ quy tắc.
    """
    return CheckConstraint(
        "(is_deleted = false AND deleted_at IS NULL AND delete_reason IS NULL)"
        " OR (is_deleted = true AND deleted_at IS NOT NULL"
        " AND delete_reason IS NOT NULL AND length(btrim(delete_reason)) > 0)",
        name="soft_delete_coherent",
    )


class PKMixin:
    id: Mapped[int] = mapped_column(primary_key=True)


class AuditMixin:
    """created_at / created_by / updated_at / updated_by."""

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    @declared_attr
    def created_by(cls) -> Mapped[int | None]:  # noqa: N805
        return mapped_column(
            ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
        )

    @declared_attr
    def updated_by(cls) -> Mapped[int | None]:  # noqa: N805
        return mapped_column(
            ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
        )


class SoftDeleteMixin:
    """is_deleted / deleted_at / deleted_by / delete_reason.

    Bảng nào có mixin này thì MỌI truy vấn mặc định phải lọc is_deleted = false.
    Dùng `session.query(...).filter_by(is_deleted=False)` hoặc repository chung.
    """

    is_deleted: Mapped[bool] = mapped_column(
        server_default=text("false"), nullable=False, index=True
    )
    deleted_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    delete_reason: Mapped[str | None] = mapped_column(String(300), nullable=True)

    @declared_attr
    def deleted_by(cls) -> Mapped[int | None]:  # noqa: N805
        return mapped_column(
            ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
        )


class BizBase(Base, PKMixin, AuditMixin, SoftDeleteMixin):
    """Bảng nghiệp vụ: có id, 4 cột audit, 4 cột xoá mềm."""

    __abstract__ = True


class LinkBase(Base):
    """Bảng nối thuần (PK kép): không có cột audit, không xoá mềm."""

    __abstract__ = True


def biz_args(*extra: Any) -> tuple[Any, ...]:
    """__table_args__ cho bảng nghiệp vụ: luôn kèm check xoá mềm."""
    return (*extra, soft_delete_coherent())


engine_kwargs: dict[str, Any] = {"pool_pre_ping": True}
if not settings.database_url.startswith("sqlite"):
    engine_kwargs.update({
        "pool_size": 15,
        "max_overflow": 25,
        "pool_recycle": 1800,
        "pool_timeout": 30,
    })

engine = create_engine(settings.database_url, **engine_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """Dependency cung cấp session DB cho FastAPI route."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

