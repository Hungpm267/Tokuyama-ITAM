"""Script dọn ghi chú và ngày bàn giao tạm từ đợt nhập Excel."""

from __future__ import annotations

import datetime as dt

from app.models import Asset, Assignment, AssetTag, AssetTagLink, AuditLog, Person
from app.services import mark_service
from scripts.cleanup_excel_import import plan_and_apply

D1016 = dt.date(2026, 10, 16)
D1102 = dt.date(2026, 11, 2)
TEMP_ASSET = "Đã bàn giao từ dữ liệu file Excel (ngày bàn giao tạm)."


def _temp(date: dt.date) -> str:
    return f"Ngày bàn giao tạm ({date.strftime('%d/%m/%Y')}) - cần sửa theo ngày thực tế. Nhập từ file Excel."


def _asset(db, seed, pc, note):
    asset = Asset(pc_name=pc, category_id=seed["cat"].id, note=note)
    db.add(asset)
    db.flush()
    return asset


def _person(db, name):
    person = Person(full_name=name)
    db.add(person)
    db.flush()
    return person


def _assign(db, asset, person, borrowed_at, note, returned_at=None):
    asgn = Assignment(asset_id=asset.id, person_id=person.id, borrowed_at=borrowed_at, note=note,
                      returned_at=returned_at)
    db.add(asgn)
    db.flush()
    return asgn


def _build(db, seed):
    p = _person(db, "Người A")
    data = {"person": p}
    data["handed"] = _asset(db, seed, "TKY-PC0101", TEMP_ASSET)
    data["handed_asgn"] = _assign(db, data["handed"], p, D1016, _temp(D1016))
    data["late"] = _asset(db, seed, "TKY-PC0102", TEMP_ASSET)
    data["late_asgn"] = _assign(db, data["late"], _person(db, "Người B"), D1102, _temp(D1102))
    data["mes"] = _asset(db, seed, "TKY-PC0060",
                         "Người dùng theo file Excel: MES system PC 08. Chưa bàn giao trong hệ thống.")
    data["purch"] = _asset(db, seed, "TKY-PC0005",
                           "Purchasing's PC - máy dùng chung của nhóm Mua hàng. Đã bàn giao từ dữ liệu file Excel (ngày bàn giao tạm).")
    data["purch_asgn"] = _assign(
        db, data["purch"], _person(db, "Pham Cu Phuong Thao"), D1016,
        "Purchasing's PC - máy dùng chung của nhóm Mua hàng, Pham Cu Phuong Thao quản lý. "
        "Ngày bàn giao tạm (16/10/2026) - cần sửa theo ngày thực tế. Nhập từ file Excel.",
    )
    data["hr"] = _asset(db, seed, "TKY-PC0002", TEMP_ASSET)
    data["hr_asgn"] = _assign(
        db, data["hr"], _person(db, "Pham Huy Chuong"), D1016,
        "HR's PC - máy dùng chung của phòng Nhân sự, Pham Huy Chuong quản lý. "
        "Ngày bàn giao tạm (16/10/2026) - cần sửa theo ngày thực tế. Nhập từ file Excel.",
    )
    data["ga"] = _asset(db, seed, "TKY-PC0070",
                        "Người dùng theo file Excel: General Affairs (Ms Tiên quản lý ). Chưa bàn giao trong hệ thống.")
    data["fin"] = _asset(db, seed, "TKY-PC0071",
                         "Người dùng theo file Excel: Financial Department (Ms Thoan quản lý). Chưa bàn giao trong hệ thống.")
    data["qa"] = _asset(db, seed, "TKY-PC0072",
                        "Người dùng theo file Excel: QA (Sakurai quản lý). Chưa bàn giao trong hệ thống.")
    data["old"] = _asset(
        db, seed, "TKY-PC0073",
        "Người dùng cũ theo file Excel: Takata Yusuke (mã NV TVC00004) - đã nghỉ việc / về nước. Máy chưa bàn giao cho ai.",
    )
    return data


def test_cleanup_applies_every_rule(db, seed):
    d = _build(db, seed)
    report = plan_and_apply(db, seed["user"].id)

    for key in ("handed_asgn", "late_asgn", "purch_asgn", "hr_asgn"):
        assert d[key].borrowed_at is None and d[key].note is None and d[key].returned_at is None
    assert report.dates_cleared == 4
    assert report.assignment_notes_cleared == 4
    assert d["handed"].note is None and d["late"].note is None
    assert report.asset_notes_cleared == 2
    assert d["mes"].note == "MES system PC 08"
    mes_mark = next(m for m in mark_service.list_marks(db) if m["name"] == "Máy MES")
    assert mes_mark["color"] == "#fef9c3" and mes_mark["count"] == 1
    assert report.mes_marked == ["TKY-PC0060"]
    assert any(m["name"] == "Không cài Zscaler" and m["count"] == 0 for m in mark_service.list_marks(db))
    assert d["purch"].note == "Máy dùng chung Mua hàng - Phạm Cù Phương Thảo quản lý"
    assert d["hr"].note == "Máy dùng chung Nhân sự - Phạm Huy Chương quản lý"
    assert d["ga"].note == "Máy dùng chung General Affairs - Ms Tiên quản lý"
    assert d["fin"].note == "Máy dùng chung phòng Tài chính - Ms Thoan quản lý"
    assert d["qa"].note == "Máy dùng chung QA - Sakurai quản lý"
    assert d["old"].note == "Người dùng cũ: Takata Yusuke (TVC00004), đã nghỉ"
    assert len(report.asset_notes_shortened) == 6
    assert db.query(AuditLog).filter(AuditLog.before_after["extra"]["source"].astext == "cleanup-excel-import").count() > 0


def test_cleanup_leaves_user_data_alone(db, seed):
    p = _person(db, "Người C")
    mine = _asset(db, seed, "TKY-PC0200", "my ntoe")
    real = _assign(db, mine, p, dt.date(2026, 9, 20), None)
    edited = _asset(db, seed, "TKY-PC0201", TEMP_ASSET)
    edited_asgn = _assign(db, edited, _person(db, "Người D"), dt.date(2026, 10, 20), _temp(D1016))
    report = plan_and_apply(db, seed["user"].id)
    assert mine.note == "my ntoe" and real.borrowed_at == dt.date(2026, 9, 20)
    assert edited_asgn.borrowed_at == dt.date(2026, 10, 20) and edited_asgn.note is None
    assert report.dates_cleared == 0
    assert any("TKY-PC0201" in line for line in report.skipped)


def test_cleanup_is_idempotent(db, seed):
    _build(db, seed)
    plan_and_apply(db, seed["user"].id)
    marks_before = len(mark_service.list_marks(db))
    again = plan_and_apply(db, seed["user"].id)
    assert (again.dates_cleared, again.assignment_notes_cleared, again.asset_notes_cleared) == (0, 0, 0)
    assert again.asset_notes_shortened == [] and again.mes_marked == []
    assert len(mark_service.list_marks(db)) == marks_before


def test_cleanup_reports_foreign_tags(db, seed):
    tag = AssetTag(code="ZSCALER", name_en="Zscaler")
    db.add(tag)
    db.flush()
    db.add(AssetTagLink(asset_id=seed["asset"].id, tag_id=tag.id))
    db.flush()
    report = plan_and_apply(db, seed["user"].id)
    assert report.foreign_tags == ["ZSCALER"]
    assert not tag.is_deleted
