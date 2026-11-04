"""Nghiệp vụ của màn hình Sổ tổng: một dòng cho mỗi laptop kèm người đang giữ.

Thay cho sheet Excel "List of TVC Employees" nên phải đủ như sheet đó: máy chưa có
người giữ và nhân viên chưa có máy đều có một dòng. Dữ liệu ở đây đi thẳng ra trình
duyệt: từ person_secrets chỉ được lấy cờ "đã có mật khẩu", không bao giờ lấy cột *_enc.

Phần mềm trên máy được đánh dấu bằng nhãn (asset_tags) có mã bắt đầu `SW-`.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.audit import record_audit
from app.core.clock import today_local
from app.enums import AuditAction, Module, PersonStatus
from app.models import Asset, AssetTag, AssetTagLink, Assignment, Department, Person, PersonSecret
from app.services.assignment_service import get_active_assignment

SOFTWARE_TAG_PREFIX = "SW-"

#: Ô sửa trực tiếp được: tên trên dòng -> (cột, độ dài tối đa, nhãn trong thông báo lỗi)
ASSET_TEXT_FIELDS = {
    "serial": ("serial", 100, "Số serial"),
    "asset_code": ("asset_code", 50, "Mã GA"),
}
PERSON_TEXT_FIELDS = {
    "email": ("email", 150, "Email"),
    "user_id": ("user_id", 50, "userId"),
}


def _person_fields(person: Person | None) -> dict[str, Any]:
    if person is None:
        return {
            "holder": None, "staff_code": None, "user_id": None, "email": None,
            "department": None, "person_status": None,
        }
    return {
        "holder": person.full_name,
        "staff_code": person.staff_code,
        "user_id": person.user_id,
        "email": person.email,
        "department": person.department.name_en if person.department else None,
        "person_status": person.status.value if person.status else None,
    }


def _row_kind(person: Person | None, note: str | None) -> str:
    """Thay cho việc tô màu tay trong Excel: xám là người đã nghỉ, vàng là máy MES."""
    if person is not None and person.status == PersonStatus.RESIGNED:
        return "resigned"
    if note and "MES" in note:
        return "mes"
    return ""


def list_software_tags(db: Session) -> list[dict[str, str]]:
    tags = db.scalars(
        select(AssetTag)
        .where(AssetTag.code.startswith(SOFTWARE_TAG_PREFIX), AssetTag.is_deleted.is_(False))
        .order_by(AssetTag.name_en)
    ).all()
    return [{"code": t.code, "name": t.name_en} for t in tags]


def list_department_names(db: Session) -> list[str]:
    return list(
        db.scalars(
            select(Department.name_en).where(Department.is_deleted.is_(False)).order_by(Department.name_en)
        ).all()
    )


def _software_by_asset(db: Session) -> dict[int, list[AssetTag]]:
    rows = db.execute(
        select(AssetTagLink.asset_id, AssetTag)
        .join(AssetTag, AssetTag.id == AssetTagLink.tag_id)
        .where(AssetTag.code.startswith(SOFTWARE_TAG_PREFIX), AssetTag.is_deleted.is_(False))
        .order_by(AssetTag.name_en)
    ).all()
    result: dict[int, list[AssetTag]] = {}
    for asset_id, tag in rows:
        result.setdefault(asset_id, []).append(tag)
    return result


def _people_with_secret(db: Session) -> set[int]:
    return set(
        db.scalars(
            select(PersonSecret.person_id).where(
                PersonSecret.pc_password_enc.is_not(None) | PersonSecret.email_password_enc.is_not(None)
            )
        ).all()
    )


def build_ledger_rows(db: Session, include_secret_flag: bool = False) -> list[dict[str, Any]]:
    """`include_secret_flag` chỉ bật cho người có quyền xem kho mật khẩu."""
    assets = db.scalars(
        select(Asset).where(Asset.is_deleted.is_(False)).order_by(Asset.pc_name, Asset.id)
    ).all()
    open_assignments = db.scalars(
        select(Assignment)
        .options(selectinload(Assignment.person).selectinload(Person.department))
        .where(Assignment.returned_at.is_(None), Assignment.is_deleted.is_(False))
    ).all()
    by_asset = {a.asset_id: a for a in open_assignments}
    persons = db.scalars(
        select(Person)
        .options(selectinload(Person.department))
        .where(Person.is_deleted.is_(False))
        .order_by(Person.staff_code)
    ).all()
    software = _software_by_asset(db)
    with_secret = _people_with_secret(db) if include_secret_flag else set()

    rows: list[dict[str, Any]] = []
    holder_ids: set[int] = set()
    for asset in assets:
        assignment = by_asset.get(asset.id)
        person = assignment.person if assignment else None
        if person is not None:
            holder_ids.add(person.id)
        tags = software.get(asset.id, [])
        rows.append({
            "id": f"asset-{asset.id}",
            "asset_id": asset.id,
            "person_id": person.id if person else None,
            "pc_name": asset.pc_name,
            "asset_code": asset.asset_code,
            "serial": asset.serial,
            "asset_status": asset.status.value if asset.status else None,
            **_person_fields(person),
            "software": ", ".join(t.name_en for t in tags) or None,
            "software_codes": [t.code for t in tags],
            "secret_set": bool(person and person.id in with_secret),
            "borrowed_at": (
                assignment.borrowed_at.strftime("%d/%m/%Y") if assignment and assignment.borrowed_at else None
            ),
            "note": asset.note,
            "row_kind": _row_kind(person, asset.note),
        })

    for person in persons:
        if person.id in holder_ids:
            continue
        rows.append({
            "id": f"person-{person.id}",
            "asset_id": None,
            "person_id": person.id,
            "pc_name": None,
            "asset_code": None,
            "serial": None,
            "asset_status": None,
            **_person_fields(person),
            "software": None,
            "software_codes": [],
            "secret_set": person.id in with_secret,
            "borrowed_at": None,
            "note": person.note,
            "row_kind": _row_kind(person, None),
        })
    return rows


def parse_row_id(raw: Any) -> tuple[str, int]:
    if isinstance(raw, str):
        kind, _, number = raw.partition("-")
        if kind in ("asset", "person") and number.isdigit() and len(number) <= 9:
            return kind, int(number)
    raise ValueError("Dòng dữ liệu không hợp lệ.")


def module_of_field(row_kind: str, field: str) -> Module:
    """Quyền sửa một ô thuộc phân hệ nào. Ô không được sửa trực tiếp thì báo lỗi."""
    if field in ASSET_TEXT_FIELDS:
        return Module.ASSETS
    if field in PERSON_TEXT_FIELDS or field == "department":
        return Module.PERSONS
    if field == "note":
        return Module.ASSETS if row_kind == "asset" else Module.PERSONS
    if field == "borrowed_at":
        return Module.ASSIGNMENTS
    raise ValueError("Ô này không sửa trực tiếp được.")


def _alive_asset(db: Session, asset_id: int) -> Asset:
    asset = db.scalar(select(Asset).where(Asset.id == asset_id, Asset.is_deleted.is_(False)))
    if not asset:
        raise ValueError("Thiết bị không tồn tại hoặc đã bị xóa.")
    return asset


def _alive_person(db: Session, person_id: int) -> Person:
    person = db.scalar(select(Person).where(Person.id == person_id, Person.is_deleted.is_(False)))
    if not person:
        raise ValueError("Nhân viên không tồn tại hoặc đã bị xóa.")
    return person


def _holder_of(db: Session, asset: Asset) -> Person:
    assignment = db.scalar(
        select(Assignment).where(
            Assignment.asset_id == asset.id,
            Assignment.returned_at.is_(None),
            Assignment.is_deleted.is_(False),
        )
    )
    if not assignment:
        raise ValueError("Máy này chưa có người giữ nên không có thông tin nhân viên để sửa.")
    return _alive_person(db, assignment.person_id)


def _reject_duplicate(db: Session, model: Any, column: str, value: str, own_id: int, label: str) -> None:
    # Chỉ số duy nhất của DB phân biệt hoa-thường; nghiệp vụ thì không.
    duplicate = db.scalar(
        select(model.id)
        .where(func.lower(getattr(model, column)) == value.lower(), model.is_deleted.is_(False), model.id != own_id)
        .limit(1)
    )
    if duplicate:
        raise ValueError(f"{label} '{value}' đã tồn tại trong hệ thống.")


def _save(db: Session, obj: Any, table: str, column: str, new_value: Any, user_id: int | None, ip: str | None) -> None:
    old_value = getattr(obj, column)
    if old_value == new_value:
        return
    setattr(obj, column, new_value)
    obj.updated_by = user_id
    obj.updated_at = dt.datetime.now(dt.timezone.utc)
    db.flush()
    record_audit(
        db=db, action=AuditAction.UPDATE, table_name=table, record_id=obj.id, user_id=user_id,
        before={column: old_value}, after={column: new_value}, ip_address=ip,
        extra={"source": "so-tong"},
    )


def _parse_date(value: str | None) -> dt.date | None:
    """Nhận dd/mm/yyyy hoặc yyyy-mm-dd; rỗng là không rõ ngày."""
    if not value:
        return None
    try:
        return dt.datetime.strptime(value, "%d/%m/%Y").date()
    except ValueError:
        pass
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        raise ValueError("Ngày bàn giao không hợp lệ (dd/mm/yyyy).") from None


def _update_borrowed_at(db: Session, asset: Asset | None, value: str | None, user_id: int | None, ip: str | None) -> None:
    """Chỉ đổi ngày của lượt đang mở: không tạo lượt mới, không đổi máy hay người."""
    assignment = get_active_assignment(db, asset.id) if asset else None
    if assignment is None:
        raise ValueError("Máy này chưa bàn giao cho ai.")
    borrowed_at = _parse_date(value)
    if borrowed_at is not None:
        if borrowed_at > today_local():
            raise ValueError("Ngày bàn giao không được ở tương lai.")
        previous_return = db.scalar(
            select(func.max(Assignment.returned_at)).where(
                Assignment.asset_id == asset.id,
                Assignment.id != assignment.id,
                Assignment.is_deleted.is_(False),
            )
        )
        if previous_return and borrowed_at < previous_return:
            raise ValueError(
                f"Ngày bàn giao không được trước ngày người trước trả máy ({previous_return.strftime('%d/%m/%Y')})."
            )
    _save(db, assignment, "assignments", "borrowed_at", borrowed_at, user_id, ip)


def update_cell(
    db: Session, row_kind: str, row_pk: int, field: str, value: str | None,
    user_id: int | None = None, ip_address: str | None = None,
) -> None:
    """Sửa một ô của Sổ tổng. Người giữ và trạng thái máy không đi qua đây: phải bàn giao / thu hồi."""
    module_of_field(row_kind, field)
    clean = value.strip() or None if isinstance(value, str) else None
    asset = _alive_asset(db, row_pk) if row_kind == "asset" else None

    if field == "borrowed_at":
        _update_borrowed_at(db, asset, clean, user_id, ip_address)
        return

    if field == "note":
        if asset:
            _save(db, asset, "assets", "note", clean, user_id, ip_address)
        else:
            _save(db, _alive_person(db, row_pk), "persons", "note", clean, user_id, ip_address)
        return

    if field in ASSET_TEXT_FIELDS:
        if asset is None:
            raise ValueError("Dòng này chưa có máy.")
        column, max_length, label = ASSET_TEXT_FIELDS[field]
        if clean and len(clean) > max_length:
            raise ValueError(f"{label} quá dài (tối đa {max_length} ký tự).")
        if clean:
            _reject_duplicate(db, Asset, column, clean, asset.id, label)
        identifiers = {"asset_code": asset.asset_code, "pc_name": asset.pc_name, "serial": asset.serial}
        identifiers[column] = clean
        if not any(identifiers.values()):
            raise ValueError("Thiết bị phải còn ít nhất một mã: mã GA, mã KDDI hoặc số serial.")
        _save(db, asset, "assets", column, clean, user_id, ip_address)
        return

    person = _holder_of(db, asset) if asset else _alive_person(db, row_pk)
    if field == "department":
        department_id = None
        if clean:
            department_id = db.scalar(
                select(Department.id).where(Department.name_en == clean, Department.is_deleted.is_(False))
            )
            if department_id is None:
                raise ValueError(f"Không có phòng ban '{clean}'.")
        _save(db, person, "persons", "department_id", department_id, user_id, ip_address)
        return

    column, max_length, label = PERSON_TEXT_FIELDS[field]
    if clean and len(clean) > max_length:
        raise ValueError(f"{label} quá dài (tối đa {max_length} ký tự).")
    if clean:
        _reject_duplicate(db, Person, column, clean, person.id, label)
    _save(db, person, "persons", column, clean, user_id, ip_address)


def set_asset_software(
    db: Session, asset_id: int, codes: list[str],
    user_id: int | None = None, ip_address: str | None = None,
) -> None:
    """Thay toàn bộ dấu phần mềm của một máy; các nhãn khác (không phải SW-) giữ nguyên."""
    asset = _alive_asset(db, asset_id)
    software_tags = {
        t.code: t
        for t in db.scalars(
            select(AssetTag).where(AssetTag.code.startswith(SOFTWARE_TAG_PREFIX), AssetTag.is_deleted.is_(False))
        ).all()
    }
    wanted = set(codes)
    unknown = wanted - software_tags.keys()
    if unknown:
        raise ValueError("Có phần mềm không nằm trong danh mục.")

    current = {
        link.tag_id: link
        for link in db.scalars(select(AssetTagLink).where(AssetTagLink.asset_id == asset.id)).all()
    }
    software_ids = {t.id for t in software_tags.values()}
    before = sorted(c for c, t in software_tags.items() if t.id in current)
    for tag_id, link in current.items():
        if tag_id in software_ids and tag_id not in {software_tags[c].id for c in wanted}:
            db.delete(link)
    for code in wanted:
        if software_tags[code].id not in current:
            db.add(AssetTagLink(asset_id=asset.id, tag_id=software_tags[code].id))
    db.flush()
    if before != sorted(wanted):
        record_audit(
            db=db, action=AuditAction.UPDATE, table_name="assets", record_id=asset.id, user_id=user_id,
            before={"software": before}, after={"software": sorted(wanted)}, ip_address=ip_address,
            extra={"source": "so-tong"},
        )
