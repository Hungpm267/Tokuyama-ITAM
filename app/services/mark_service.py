"""Kiểu đánh dấu màu cho máy trên Sổ tổng.

Một kiểu đánh dấu là một nhãn `asset_tags` có mã `MARK-…` và màu `#rrggbb`, gắn cho máy
qua `asset_tag_links`. Mỗi máy mang tối đa một kiểu; nhãn phần mềm `SW-` không bị đụng.
"""

from __future__ import annotations

import datetime as dt
import re
import unicodedata
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.audit import record_audit
from app.enums import AuditAction
from app.models import Asset, AssetTag, AssetTagLink

MARK_TAG_PREFIX = "MARK-"
SOFTWARE_TAG_PREFIX = "SW-"
_COLOR = re.compile(r"#[0-9a-fA-F]{6}")
_CODE_MAX = 30
_NAME_MAX = 100


def _audit(db: Session, action: AuditAction, table: str, record_id: int, user_id: int | None, ip: str | None,
           before: dict | None = None, after: dict | None = None) -> None:
    record_audit(
        db=db, action=action, table_name=table, record_id=record_id, user_id=user_id,
        before=before, after=after, ip_address=ip, extra={"source": "so-tong"},
    )


_KIND = {MARK_TAG_PREFIX: "kiểu đánh dấu", SOFTWARE_TAG_PREFIX: "phần mềm"}


def _alive_tags(db: Session, prefix: str) -> list[AssetTag]:
    return db.scalars(
        select(AssetTag)
        .where(AssetTag.code.startswith(prefix), AssetTag.is_deleted.is_(False))
        .order_by(func.lower(AssetTag.name_en), AssetTag.id)
    ).all()


def _alive_tag(db: Session, tag_id: int, prefix: str) -> AssetTag:
    tag = db.get(AssetTag, tag_id)
    if tag is None or tag.is_deleted or not tag.code.startswith(prefix):
        raise ValueError(f"Không có {_KIND[prefix]} này.")
    return tag


def _alive_marks(db: Session) -> list[AssetTag]:
    return _alive_tags(db, MARK_TAG_PREFIX)


def _alive_mark(db: Session, tag_id: int) -> AssetTag:
    return _alive_tag(db, tag_id, MARK_TAG_PREFIX)


def _clean_name(db: Session, name: Any, own_id: int | None = None, prefix: str = MARK_TAG_PREFIX) -> str:
    kind = _KIND[prefix]
    clean = name.strip() if isinstance(name, str) else ""
    if not clean:
        raise ValueError(f"Tên {kind} không được để trống.")
    if len(clean) > _NAME_MAX:
        raise ValueError(f"Tên {kind} quá dài (tối đa {_NAME_MAX} ký tự).")
    for tag in _alive_tags(db, prefix):
        if tag.id != own_id and tag.name_en.lower() == clean.lower():
            raise ValueError(f"Đã có {kind} '{tag.name_en}'.")
    return clean


def _clean_color(color: Any) -> str:
    if not isinstance(color, str) or not _COLOR.fullmatch(color.strip()):
        raise ValueError("Màu phải có dạng #rrggbb.")
    return color.strip().lower()


def _new_code(db: Session, name: str, prefix: str = MARK_TAG_PREFIX) -> str:
    """Mã sinh từ tên: bỏ dấu, in hoa; tên không có chữ Latin thì dùng số thứ tự."""
    ascii_name = unicodedata.normalize("NFKD", name.replace("đ", "d").replace("Đ", "D"))
    ascii_name = ascii_name.encode("ascii", "ignore").decode()
    slug = re.sub(r"[^A-Z0-9]+", "-", ascii_name.upper()).strip("-")
    base = (prefix + slug)[:_CODE_MAX - 3].rstrip("-") if slug else prefix.rstrip("-")
    taken = set(db.scalars(select(AssetTag.code).where(AssetTag.is_deleted.is_(False))).all())
    if slug and base not in taken:
        return base
    number = 1 if slug else 0
    while True:
        number += 1
        code = f"{base}-{number}"
        if code not in taken:
            return code


def list_marks(db: Session) -> list[dict[str, Any]]:
    counts = dict(
        db.execute(
            select(AssetTagLink.tag_id, func.count())
            .join(Asset, Asset.id == AssetTagLink.asset_id)
            .where(Asset.is_deleted.is_(False))
            .group_by(AssetTagLink.tag_id)
        ).all()
    )
    return [
        {"id": t.id, "code": t.code, "name": t.name_en, "color": t.color, "count": counts.get(t.id, 0)}
        for t in _alive_marks(db)
    ]


def create_mark(db: Session, name: Any, color: Any, user_id: int | None, ip_address: str | None) -> AssetTag:
    clean_name = _clean_name(db, name)
    clean_color = _clean_color(color)
    tag = AssetTag(
        code=_new_code(db, clean_name), name_en=clean_name, color=clean_color,
        created_by=user_id, updated_by=user_id,
    )
    db.add(tag)
    db.flush()
    _audit(db, AuditAction.CREATE, "asset_tags", tag.id, user_id, ip_address,
           after={"code": tag.code, "name_en": tag.name_en, "color": tag.color})
    return tag


def update_mark(db: Session, tag_id: int, name: Any, color: Any, user_id: int | None, ip_address: str | None) -> AssetTag:
    tag = _alive_mark(db, tag_id)
    clean_name = _clean_name(db, name, own_id=tag.id)
    clean_color = _clean_color(color)
    before = {"name_en": tag.name_en, "color": tag.color}
    if (clean_name, clean_color) == (tag.name_en, tag.color):
        return tag
    tag.name_en, tag.color, tag.updated_by = clean_name, clean_color, user_id
    db.flush()
    _audit(db, AuditAction.UPDATE, "asset_tags", tag.id, user_id, ip_address,
           before=before, after={"name_en": clean_name, "color": clean_color})
    return tag


def delete_mark(db: Session, tag_id: int, user_id: int | None, ip_address: str | None) -> int:
    """Gỡ kiểu đánh dấu khỏi mọi máy rồi xóa mềm. Trả số máy bị gỡ."""
    tag = _alive_mark(db, tag_id)
    links = db.scalars(select(AssetTagLink).where(AssetTagLink.tag_id == tag.id)).all()
    for link in links:
        _audit(db, AuditAction.UPDATE, "assets", link.asset_id, user_id, ip_address,
               before={"mark": tag.name_en}, after={"mark": None})
        db.delete(link)
    tag.is_deleted = True
    tag.deleted_at = dt.datetime.now(dt.timezone.utc)
    tag.deleted_by = user_id
    tag.delete_reason = "Xóa kiểu đánh dấu trên Sổ tổng"
    db.flush()
    _audit(db, AuditAction.DELETE, "asset_tags", tag.id, user_id, ip_address,
           before={"code": tag.code, "name_en": tag.name_en, "color": tag.color})
    return len(links)


def set_asset_mark(db: Session, asset_id: int, tag_id: int | None, user_id: int | None, ip_address: str | None) -> None:
    """Đặt kiểu đánh dấu duy nhất cho máy; None là bỏ đánh dấu."""
    asset = db.get(Asset, asset_id)
    if asset is None or asset.is_deleted:
        raise ValueError("Không tìm thấy thiết bị.")
    wanted = _alive_mark(db, tag_id) if tag_id is not None else None
    current = db.execute(
        select(AssetTagLink, AssetTag)
        .join(AssetTag, AssetTag.id == AssetTagLink.tag_id)
        .where(AssetTagLink.asset_id == asset.id, AssetTag.code.startswith(MARK_TAG_PREFIX))
    ).all()
    before = next((tag.name_en for _, tag in current if not tag.is_deleted), None)
    if wanted is not None and [tag.id for _, tag in current] == [wanted.id]:
        return
    for link, _ in current:
        db.delete(link)
    if wanted is not None:
        db.add(AssetTagLink(asset_id=asset.id, tag_id=wanted.id))
    db.flush()
    after = wanted.name_en if wanted else None
    if before != after:
        _audit(db, AuditAction.UPDATE, "assets", asset.id, user_id, ip_address,
               before={"mark": before}, after={"mark": after})


def marks_by_asset(db: Session) -> dict[int, dict[str, Any]]:
    """Kiểu đánh dấu đang gắn trên từng máy, cho Sổ tổng."""
    rows = db.execute(
        select(AssetTagLink.asset_id, AssetTag)
        .join(AssetTag, AssetTag.id == AssetTagLink.tag_id)
        .where(AssetTag.code.startswith(MARK_TAG_PREFIX), AssetTag.is_deleted.is_(False))
    ).all()
    return {asset_id: {"id": tag.id, "name": tag.name_en, "color": tag.color} for asset_id, tag in rows}


# --- Danh mục phần mềm (SW-) ----------------------------------------------------------


def list_software(db: Session) -> list[dict[str, Any]]:
    counts = dict(
        db.execute(
            select(AssetTagLink.tag_id, func.count())
            .join(Asset, Asset.id == AssetTagLink.asset_id)
            .where(Asset.is_deleted.is_(False))
            .group_by(AssetTagLink.tag_id)
        ).all()
    )
    return [
        {"id": t.id, "code": t.code, "name": t.name_en, "count": counts.get(t.id, 0)}
        for t in _alive_tags(db, SOFTWARE_TAG_PREFIX)
    ]


def create_software(db: Session, name: Any, user_id: int | None, ip_address: str | None) -> AssetTag:
    clean_name = _clean_name(db, name, prefix=SOFTWARE_TAG_PREFIX)
    tag = AssetTag(
        code=_new_code(db, clean_name, SOFTWARE_TAG_PREFIX), name_en=clean_name,
        created_by=user_id, updated_by=user_id,
    )
    db.add(tag)
    db.flush()
    _audit(db, AuditAction.CREATE, "asset_tags", tag.id, user_id, ip_address,
           after={"code": tag.code, "name_en": tag.name_en})
    return tag


def update_software(db: Session, tag_id: int, name: Any, user_id: int | None, ip_address: str | None) -> AssetTag:
    tag = _alive_tag(db, tag_id, SOFTWARE_TAG_PREFIX)
    clean_name = _clean_name(db, name, own_id=tag.id, prefix=SOFTWARE_TAG_PREFIX)
    if clean_name == tag.name_en:
        return tag
    before = tag.name_en
    tag.name_en, tag.updated_by = clean_name, user_id
    db.flush()
    _audit(db, AuditAction.UPDATE, "asset_tags", tag.id, user_id, ip_address,
           before={"name_en": before}, after={"name_en": clean_name})
    return tag


def delete_software(db: Session, tag_id: int, user_id: int | None, ip_address: str | None) -> int:
    """Gỡ phần mềm khỏi mọi máy rồi xóa mềm. Trả số máy bị gỡ."""
    tag = _alive_tag(db, tag_id, SOFTWARE_TAG_PREFIX)
    links = db.scalars(select(AssetTagLink).where(AssetTagLink.tag_id == tag.id)).all()
    for link in links:
        _audit(db, AuditAction.UPDATE, "assets", link.asset_id, user_id, ip_address,
               before={"software": tag.name_en}, after={"software": None})
        db.delete(link)
    tag.is_deleted = True
    tag.deleted_at = dt.datetime.now(dt.timezone.utc)
    tag.deleted_by = user_id
    tag.delete_reason = "Xóa phần mềm khỏi danh mục trên Sổ tổng"
    db.flush()
    _audit(db, AuditAction.DELETE, "asset_tags", tag.id, user_id, ip_address,
           before={"code": tag.code, "name_en": tag.name_en})
    return len(links)
