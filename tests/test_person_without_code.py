"""Nhân sự không có mã nhân viên: mã được để trống, mã có giá trị vẫn phải duy nhất."""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.clock import today_local
from app.enums import PersonStatus
from app.models import Asset, Person
from app.services.assignment_service import assign_asset
from app.services.ledger_service import build_ledger_rows
from tests.test_so_tong_edit import admin_client, client, override_db  # noqa: F401

PAST = today_local() - dt.timedelta(days=30)


def _no_code(db, name="Takeda Aki"):
    person = Person(staff_code=None, full_name=name, status=PersonStatus.ACTIVE)
    db.add(person)
    db.flush()
    return person


def test_many_people_can_have_no_code(db, seed):
    assert _no_code(db, "A").id != _no_code(db, "B").id


def test_a_real_code_is_still_unique(db, seed):
    db.add(Person(staff_code="TVC00001", full_name="Trung ma"))
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_label_has_no_none_text(db, seed):
    person = _no_code(db)
    assert str(person) == "Takeda Aki"
    assert "None" not in str(person)


def test_person_without_code_can_be_assigned_and_shows_in_ledger(db, seed):
    person = _no_code(db)
    assign_asset(db, seed["asset"].id, person.id, PAST)
    row = next(r for r in build_ledger_rows(db) if r["asset_id"] == seed["asset"].id)
    assert row["holder"] == "Takeda Aki"
    assert row["staff_code"] is None
    db.refresh(seed["asset"], ["assignments"])
    assert seed["asset"].current_holder == "Takeda Aki"


def test_person_form_saves_with_blank_code(admin_client, db, seed):  # noqa: F811
    res = admin_client.post(
        "/admin/person/create",
        data={"full_name": "Sugimoto Hirokazu", "staff_code": "", "status": "ACTIVE"},
        follow_redirects=True,
    )
    assert res.status_code == 200
    person = db.scalar(select(Person).where(Person.full_name == "Sugimoto Hirokazu"))
    assert person is not None and person.staff_code is None


def test_pages_do_not_print_none_for_missing_code(admin_client, db, seed):  # noqa: F811
    person = _no_code(db, "Hoang Duc Long")
    assign_asset(db, seed["asset"].id, person.id, PAST)
    history = admin_client.get(f"/admin/assets/{seed['asset'].id}/history").json()
    assert history[0]["staff_code"] == ""
    search = admin_client.get("/admin/api/persons/search?q=Hoang").json()
    assert search[0]["staff_code"] == ""
    for path in (f"/admin/person/details/{person.id}", "/admin/person-secret/list", "/admin/global-search?q=Hoang"):
        res = admin_client.get(path)
        assert res.status_code == 200
        assert "Hoang Duc Long (None)" not in res.text
        assert ">None<" not in res.text


def test_restoring_a_person_without_code_works(admin_client, db, seed):  # noqa: F811
    person = _no_code(db)
    person.is_deleted = True
    person.deleted_at = dt.datetime.now(dt.timezone.utc)
    person.delete_reason = "test"
    db.flush()
    assert admin_client.get("/admin/trash?entity=person").status_code == 200
    res = admin_client.post("/admin/trash/restore", data={"entity_type": "person", "item_id": person.id})
    assert res.status_code == 200, res.text
    assert person.is_deleted is False


def test_asset_without_holder_code_still_listed(db, seed):
    other = Asset(vendor_code="TKY-PC0777", category_id=seed["cat"].id)
    db.add(other)
    db.flush()
    assign_asset(db, other.id, _no_code(db, "Katou").id, PAST)
    assert any(r["pc_name"] == "TKY-PC0777" and r["holder"] == "Katou" for r in build_ledger_rows(db))
