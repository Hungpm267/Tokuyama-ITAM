"""Loại nhân sự và mã tự cấp: VND-NNN cho vendor, JP-NNN cho người công tác Nhật."""

from __future__ import annotations

import asyncio
import datetime as dt

import pytest

from app.admin import PersonAdmin
from app.enums import PersonStatus, PersonType
from app.models import Person
from app.services.ledger_service import build_ledger_rows
from app.services.person_code_service import next_code, resolve_code
from tests.test_so_tong_edit import admin_client, client, override_db  # noqa: F401
from tests.test_wave4_logic_audit import DummyRequest


def _person(db, code, kind=PersonType.VENDOR, deleted=False):
    person = Person(full_name=f"P {code}", staff_code=code, person_type=kind, status=PersonStatus.ACTIVE)
    if deleted:
        person.is_deleted = True
        person.deleted_at = dt.datetime.now(dt.timezone.utc)
        person.delete_reason = "test"
    db.add(person)
    db.flush()
    return person


def test_next_vendor_code_starts_at_001(db, seed):
    assert next_code(db, PersonType.VENDOR) == "VND-001"
    assert next_code(db, PersonType.BUSINESS_TRIP) == "JP-001"


def test_next_code_never_reuses_a_deleted_code(db, seed):
    _person(db, "VND-001")
    _person(db, "VND-007", deleted=True)
    assert next_code(db, PersonType.VENDOR) == "VND-008"


def test_next_code_ignores_hand_typed_codes_not_matching_pattern(db, seed):
    _person(db, "VND-ABC")
    assert next_code(db, PersonType.VENDOR) == "VND-001"


@pytest.mark.parametrize("kind,code,expected", [
    (PersonType.EMPLOYEE, "TVC00099", "TVC00099"),
    (PersonType.VENDOR, None, "VND-001"),
    (PersonType.VENDOR, "  ", "VND-001"),
    (PersonType.BUSINESS_TRIP, "JP-010", "JP-010"),
    (PersonType.BUSINESS_TRIP, "jp-010", "JP-010"),
])
def test_resolve_code_accepts(db, seed, kind, code, expected):
    assert resolve_code(db, kind, code) == expected


@pytest.mark.parametrize("kind,code", [
    (PersonType.EMPLOYEE, None),
    (PersonType.EMPLOYEE, "VND-001"),
    (PersonType.EMPLOYEE, "jp-004"),
    (PersonType.VENDOR, "TVC00099"),
    (PersonType.BUSINESS_TRIP, "VND-002"),
])
def test_resolve_code_refuses(db, seed, kind, code):
    with pytest.raises(ValueError):
        resolve_code(db, kind, code)


def _form(db, seed, data, model=None):
    request = DummyRequest(session={"user_id": seed["user"].id}, db=db)
    asyncio.run(PersonAdmin().on_model_change(data, model or Person(), model is None, request))
    return data


def test_person_form_assigns_code_for_vendor(db, seed):
    data = _form(db, seed, {"full_name": "Vendor X", "person_type": "VENDOR", "staff_code": None, "status": "ACTIVE"})
    assert data["staff_code"] == "VND-001"


def test_person_form_refuses_employee_without_code(db, seed):
    with pytest.raises(ValueError):
        _form(db, seed, {"full_name": "Emp X", "person_type": "EMPLOYEE", "staff_code": None, "status": "ACTIVE"})


def test_person_form_switching_vendor_to_employee_needs_a_real_code(db, seed):
    vendor = _person(db, "VND-001")
    with pytest.raises(ValueError):
        _form(db, seed, {"person_type": "EMPLOYEE", "staff_code": "VND-001"}, model=vendor)


def test_person_form_keeps_type_when_not_in_data(db, seed):
    vendor = _person(db, "VND-001")
    data = _form(db, seed, {"full_name": "Renamed"}, model=vendor)
    assert data.get("staff_code", "VND-001") == "VND-001"


def test_ledger_row_has_person_type(db, seed):
    rows = build_ledger_rows(db)
    row = next(r for r in rows if r["staff_code"] == "TVC00001")
    assert row["person_type"] == "EMPLOYEE"


def test_person_list_shows_type_label(admin_client, db, seed):  # noqa: F811
    _person(db, "VND-001")
    html = admin_client.get("/admin/person/list").text
    assert "Vendor" in html and "Nhân viên chính thức" in html


def test_person_create_form_assigns_vendor_code_when_code_left_blank(admin_client, db, seed):  # noqa: F811
    res = admin_client.post("/admin/person/create", data={
        "full_name": "Vendor Qua Form", "person_type": "VENDOR", "staff_code": "", "status": "ACTIVE",
    }, follow_redirects=False)
    assert res.status_code in (302, 303), res.text[:300]
    person = db.query(Person).filter_by(full_name="Vendor Qua Form").one()
    assert person.staff_code == "VND-001"


def test_person_form_shows_readable_type_choices(admin_client, db, seed):  # noqa: F811
    html = admin_client.get("/admin/person/create").text
    assert "Công tác Nhật" in html
    assert ">BUSINESS_TRIP<" not in html
