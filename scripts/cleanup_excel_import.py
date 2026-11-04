"""Dọn ghi chú và ngày bàn giao tạm mà agent tự ghi khi nhập file Excel (chạy một lần).

Chỉ đổi dòng còn khớp CHÍNH XÁC nội dung lúc nhập. Dòng người dùng đã sửa thì bỏ qua và
liệt kê trong báo cáo. Chạy lại lần hai không đổi gì.

    python -m scripts.cleanup_excel_import            # chạy thử, rollback
    python -m scripts.cleanup_excel_import --apply    # ghi thật

Script dùng database trong ITAM_DATABASE_URL (.env đang trỏ Aiven): chỉ chạy --apply trên
Aiven khi người dùng cho phép, sau khi đã sao lưu.
"""

from __future__ import annotations

import datetime as dt
import re
import sys
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import record_audit
from app.enums import AuditAction
from app.models import Asset, AssetTag, Assignment, User
from app.services import mark_service

TEMP_DATES = {dt.date(2026, 10, 16), dt.date(2026, 11, 2)}
TEMP_ASSET_NOTE = "Đã bàn giao từ dữ liệu file Excel (ngày bàn giao tạm)."
_TEMP_ASSIGNMENT = re.compile(
    r"Ngày bàn giao tạm \((\d{2}/\d{2}/\d{4})\) - cần sửa theo ngày thực tế\. Nhập từ file Excel\."
)
_SHARED_PREFIXES = ("HR's PC - ", "Purchasing's PC - ")
_MES = re.compile(r"Người dùng theo file Excel: MES system PC (\d+)\. Chưa bàn giao trong hệ thống\.")
_OLD_USER = re.compile(
    r"Người dùng cũ theo file Excel: (.+) \(mã NV (TVC\d+)\) - đã nghỉ việc / về nước\. Máy chưa bàn giao cho ai\."
)
SHORT_NOTES = {
    "Purchasing's PC - máy dùng chung của nhóm Mua hàng. Đã bàn giao từ dữ liệu file Excel (ngày bàn giao tạm).":
        "Máy dùng chung Mua hàng - Phạm Cù Phương Thảo quản lý",
    "Người dùng theo file Excel: General Affairs (Ms Tiên quản lý ). Chưa bàn giao trong hệ thống.":
        "Máy dùng chung General Affairs - Ms Tiên quản lý",
    "Người dùng theo file Excel: Financial Department (Ms Thoan quản lý). Chưa bàn giao trong hệ thống.":
        "Máy dùng chung phòng Tài chính - Ms Thoan quản lý",
    "Người dùng theo file Excel: QA (Sakurai quản lý). Chưa bàn giao trong hệ thống.":
        "Máy dùng chung QA - Sakurai quản lý",
}
HR_NOTE = "Máy dùng chung Nhân sự - Phạm Huy Chương quản lý"
MARKS = (("Máy MES", "#fef9c3"), ("Không cài Zscaler", "#fecaca"))
SOURCE = {"source": "cleanup-excel-import"}


@dataclass
class CleanupReport:
    dates_cleared: int = 0
    assignment_notes_cleared: int = 0
    asset_notes_cleared: int = 0
    asset_notes_shortened: list[tuple[str, str]] = field(default_factory=list)
    mes_marked: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    foreign_tags: list[str] = field(default_factory=list)


def _set(db: Session, obj, table: str, values: dict, actor_id: int) -> None:
    before = {k: getattr(obj, k) for k in values}
    for key, value in values.items():
        setattr(obj, key, value)
    obj.updated_by = actor_id
    db.flush()
    record_audit(
        db=db, action=AuditAction.UPDATE, table_name=table, record_id=obj.id, user_id=actor_id,
        before={k: v.isoformat() if isinstance(v, dt.date) else v for k, v in before.items()},
        after={k: v.isoformat() if isinstance(v, dt.date) else v for k, v in values.items()},
        extra=SOURCE,
    )


def _label(asset: Asset | None) -> str:
    return (asset.pc_name or asset.serial or f"#{asset.id}") if asset else "?"


def _temp_date(note: str | None) -> dt.date | None | bool:
    """Ngày tạm ghi trong ghi chú; False nếu ghi chú không phải của đợt nhập Excel."""
    if not note:
        return False
    text = note
    if note.startswith(_SHARED_PREFIXES):
        index = note.find("Ngày bàn giao tạm (")
        if index < 0:
            return False
        text = note[index:]
    match = _TEMP_ASSIGNMENT.fullmatch(text)
    if not match:
        return False
    return dt.datetime.strptime(match.group(1), "%d/%m/%Y").date()


def _ensure_marks(db: Session, actor_id: int) -> int:
    existing = {m["name"].lower(): m["id"] for m in mark_service.list_marks(db)}
    for name, color in MARKS:
        if name.lower() not in existing:
            existing[name.lower()] = mark_service.create_mark(db, name, color, user_id=actor_id, ip_address=None).id
    return existing[MARKS[0][0].lower()]


def plan_and_apply(db: Session, actor_id: int) -> CleanupReport:
    """Áp mọi luật lên session; người gọi tự commit hoặc rollback."""
    report = CleanupReport()
    hr_assets: set[int] = set()

    assignments = db.scalars(
        select(Assignment).where(Assignment.is_deleted.is_(False), Assignment.note.is_not(None)).order_by(Assignment.id)
    ).all()
    for asgn in assignments:
        temp = _temp_date(asgn.note)
        if temp is False:
            continue
        asset = db.get(Asset, asgn.asset_id)
        if asgn.note.startswith("HR's PC - "):
            hr_assets.add(asgn.asset_id)
        values: dict = {"note": None}
        if asgn.returned_at is None and asgn.borrowed_at == temp and temp in TEMP_DATES:
            values["borrowed_at"] = None
            report.dates_cleared += 1
        else:
            reason = "lượt đã trả máy" if asgn.returned_at else f"ngày {asgn.borrowed_at} đã được sửa"
            report.skipped.append(f"{_label(asset)}: {reason}, giữ ngày, chỉ xóa ghi chú")
        _set(db, asgn, "assignments", values, actor_id)
        report.assignment_notes_cleared += 1

    mes_mark_id = _ensure_marks(db, actor_id)
    assets = db.scalars(
        select(Asset).where(Asset.is_deleted.is_(False)).order_by(Asset.pc_name, Asset.id)
    ).all()
    for asset in assets:
        note = asset.note
        if asset.id in hr_assets:
            if note in (None, TEMP_ASSET_NOTE):
                _set(db, asset, "assets", {"note": HR_NOTE}, actor_id)
                report.asset_notes_shortened.append((_label(asset), HR_NOTE))
            else:
                report.skipped.append(f"{_label(asset)}: máy HR đã có ghi chú khác, giữ nguyên")
            continue
        if note == TEMP_ASSET_NOTE:
            _set(db, asset, "assets", {"note": None}, actor_id)
            report.asset_notes_cleared += 1
        elif note in SHORT_NOTES:
            _set(db, asset, "assets", {"note": SHORT_NOTES[note]}, actor_id)
            report.asset_notes_shortened.append((_label(asset), SHORT_NOTES[note]))
        elif note and (match := _MES.fullmatch(note)):
            mark_service.set_asset_mark(db, asset.id, mes_mark_id, user_id=actor_id, ip_address=None)
            _set(db, asset, "assets", {"note": f"MES system PC {match.group(1)}"}, actor_id)
            report.mes_marked.append(_label(asset))
        elif note and (match := _OLD_USER.fullmatch(note)):
            short = f"Người dùng cũ: {match.group(1)} ({match.group(2)}), đã nghỉ"
            _set(db, asset, "assets", {"note": short}, actor_id)
            report.asset_notes_shortened.append((_label(asset), short))

    report.foreign_tags = list(db.scalars(
        select(AssetTag.code).where(
            AssetTag.is_deleted.is_(False),
            ~AssetTag.code.startswith("SW-"),
            ~AssetTag.code.startswith(mark_service.MARK_TAG_PREFIX),
        ).order_by(AssetTag.code)
    ).all())
    return report


def main(argv: list[str]) -> int:
    from sqlalchemy.engine import make_url

    from app.config import settings
    from app.db import SessionLocal

    apply = "--apply" in argv
    url = make_url(settings.database_url)
    print(f"Database: {url.host} / {url.database}  -  {'GHI THẬT' if apply else 'CHẠY THỬ (rollback)'}")
    with SessionLocal() as db:
        actor = db.scalar(select(User).where(User.username == "manhhung", User.is_deleted.is_(False)))
        if actor is None:
            print("Không tìm thấy tài khoản manhhung, dừng.")
            return 1
        report = plan_and_apply(db, actor.id)
        print(f"Ngày bàn giao tạm xóa trống: {report.dates_cleared}")
        print(f"Ghi chú lượt bàn giao xóa:   {report.assignment_notes_cleared}")
        print(f"Ghi chú máy xóa:             {report.asset_notes_cleared}")
        print(f"Máy gắn 'Máy MES':           {len(report.mes_marked)}  {', '.join(report.mes_marked)}")
        print(f"Ghi chú máy rút gọn:         {len(report.asset_notes_shortened)}")
        for pc, note in report.asset_notes_shortened:
            print(f"    {pc}: {note}")
        print(f"Bỏ qua:                      {len(report.skipped)}")
        for line in report.skipped:
            print(f"    {line}")
        if report.foreign_tags:
            print(f"Nhãn lạ (để nguyên):         {', '.join(report.foreign_tags)}")
        if apply:
            db.commit()
            print("ĐÃ GHI.")
        else:
            db.rollback()
            print("Chưa ghi gì. Thêm --apply để ghi thật.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
