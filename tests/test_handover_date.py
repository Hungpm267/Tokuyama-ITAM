"""Ngày bàn giao: để trống được (không rõ ngày), sửa và xóa trống trên Sổ tổng."""

from __future__ import annotations

import asyncio
import datetime as dt

from sqlalchemy import inspect

from app.admin import AssignmentAdmin
from app.models import Assignment
from app.services.ledger_service import build_ledger_rows
from tests.test_so_tong_edit import admin_client, client, override_db  # noqa: F401
from tests.test_wave4_logic_audit import DummyRequest


def _open(db, seed, borrowed_at=None, person="person"):
    asgn = Assignment(asset_id=seed["asset"].id, person_id=seed[person].id, borrowed_at=borrowed_at)
    db.add(asgn)
    db.flush()
    return asgn


def test_open_assignment_can_have_no_date(db, seed):
    assert _open(db, seed).borrowed_at is None


def test_closed_assignment_without_start_date_is_allowed(db, seed):
    asgn = Assignment(
        asset_id=seed["asset"].id, person_id=seed["person"].id, borrowed_at=None, returned_at=dt.date(2026, 10, 1)
    )
    db.add(asgn)
    db.flush()


def test_borrowed_at_column_is_nullable(db):
    cols = {c["name"]: c for c in inspect(db.connection()).get_columns("assignments")}
    assert cols["borrowed_at"]["nullable"] is True


def test_ledger_shows_blank_date(db, seed):
    _open(db, seed)
    row = next(r for r in build_ledger_rows(db) if r["id"] == f"asset-{seed['asset'].id}")
    assert row["holder"] == seed["person"].full_name
    assert row["borrowed_at"] is None


def test_detail_pages_render_with_mixed_dates(admin_client, db, seed):  # noqa: F811
    db.add(Assignment(
        asset_id=seed["asset"].id, person_id=seed["person"].id,
        borrowed_at=dt.date(2026, 9, 1), returned_at=dt.date(2026, 9, 10),
    ))
    db.flush()
    _open(db, seed)
    assert admin_client.get(f"/admin/asset/details/{seed['asset'].id}").status_code == 200
    assert admin_client.get(f"/admin/person/details/{seed['person'].id}").status_code == 200


def test_admin_form_saves_empty_date_as_null(db, seed):
    data = {"asset": str(seed["asset"].id), "person": str(seed["person"].id), "borrowed_at": None, "returned_at": None}
    request = DummyRequest(session={"user_id": seed["user"].id}, db=db)
    asyncio.run(AssignmentAdmin().on_model_change(data, Assignment(), True, request))
    assert data["borrowed_at"] is None


def test_admin_form_overlap_check_tolerates_history_without_start_date(db, seed):
    db.add(Assignment(asset_id=seed["asset"].id, person_id=seed["person"].id, borrowed_at=None,
                      returned_at=dt.date(2026, 9, 10)))
    db.flush()
    data = {"asset": str(seed["asset"].id), "person": str(seed["person_b"].id),
            "borrowed_at": dt.date(2026, 9, 15), "returned_at": dt.date(2026, 9, 20)}
    request = DummyRequest(session={"user_id": seed["user"].id}, db=db)
    asyncio.run(AssignmentAdmin().on_model_change(data, Assignment(), True, request))


def test_machine_with_unknown_date_can_be_returned(db, seed):
    from app.services.assignment_service import return_asset

    asgn = _open(db, seed)
    return_asset(db, seed["asset"].id, dt.date(2026, 10, 1), user_id=seed["user"].id)
    assert asgn.returned_at == dt.date(2026, 10, 1)


# --- Sửa ngày trên Sổ tổng -------------------------------------------------------

import pytest  # noqa: E402

from app.core.clock import today_local  # noqa: E402
from app.models import AuditLog  # noqa: E402
from tests.test_so_tong_edit import _login, _patch, _viewer  # noqa: E402
from app.enums import RoleCode  # noqa: E402


def _row_id(seed):
    return f"asset-{seed['asset'].id}"


def test_edit_date_accepts_both_formats(admin_client, db, seed):  # noqa: F811
    asgn = _open(db, seed, dt.date(2026, 10, 16))
    assert _patch(admin_client, _row_id(seed), "borrowed_at", "15/09/2026").status_code == 200
    assert asgn.borrowed_at == dt.date(2026, 9, 15)
    assert _patch(admin_client, _row_id(seed), "borrowed_at", "2026-09-14").status_code == 200
    assert asgn.borrowed_at == dt.date(2026, 9, 14)
    assert db.query(AuditLog).filter_by(table_name="assignments", record_id=asgn.id).count() == 2


def test_clear_date_keeps_holder(admin_client, db, seed):  # noqa: F811
    asgn = _open(db, seed, dt.date(2026, 10, 16))
    res = _patch(admin_client, _row_id(seed), "borrowed_at", "")
    assert res.status_code == 200
    assert asgn.borrowed_at is None and asgn.returned_at is None
    assert asgn.person_id == seed["person"].id
    row = next(r for r in res.json()["rows"] if r["id"] == _row_id(seed))
    assert row["borrowed_at"] is None and row["holder"] == seed["person"].full_name


@pytest.mark.parametrize("value", ["abc", "31/02/2026", "15-09-2026x", "2026/13/01"])
def test_bad_date_is_400(admin_client, db, seed, value):  # noqa: F811
    asgn = _open(db, seed, dt.date(2026, 10, 16))
    assert _patch(admin_client, _row_id(seed), "borrowed_at", value).status_code == 400
    assert asgn.borrowed_at == dt.date(2026, 10, 16)


def test_future_date_is_refused(admin_client, db, seed):  # noqa: F811
    _open(db, seed, dt.date(2026, 10, 16))
    tomorrow = (today_local() + dt.timedelta(days=1)).strftime("%d/%m/%Y")
    assert _patch(admin_client, _row_id(seed), "borrowed_at", tomorrow).status_code == 400


def test_date_cannot_overlap_previous_holder(admin_client, db, seed):  # noqa: F811
    db.add(Assignment(asset_id=seed["asset"].id, person_id=seed["person_b"].id,
                      borrowed_at=dt.date(2026, 9, 1), returned_at=dt.date(2026, 9, 20)))
    db.flush()
    _open(db, seed, dt.date(2026, 10, 16))
    assert _patch(admin_client, _row_id(seed), "borrowed_at", "10/09/2026").status_code == 400


def test_date_may_equal_previous_return_date(admin_client, db, seed):  # noqa: F811
    db.add(Assignment(asset_id=seed["asset"].id, person_id=seed["person_b"].id,
                      borrowed_at=dt.date(2026, 9, 1), returned_at=dt.date(2026, 9, 20)))
    db.flush()
    _open(db, seed, dt.date(2026, 10, 16))
    assert _patch(admin_client, _row_id(seed), "borrowed_at", "20/09/2026").status_code == 200


@pytest.mark.parametrize("row", ["asset", "person"])
def test_row_without_open_assignment_refuses_date(admin_client, db, seed, row):  # noqa: F811
    row_id = _row_id(seed) if row == "asset" else f"person-{seed['person'].id}"
    assert _patch(admin_client, row_id, "borrowed_at", "01/10/2026").status_code == 400


def test_view_only_user_cannot_edit_date(client, db, seed):  # noqa: F811
    asgn = _open(db, seed, dt.date(2026, 10, 16))
    _login(client, _viewer(db, "date_viewer"), RoleCode.EXECUTIVE.value)
    assert _patch(client, _row_id(seed), "borrowed_at", "01/10/2026").status_code == 403
    assert asgn.borrowed_at == dt.date(2026, 10, 16)


def test_admin_form_blank_date_still_refuses_second_open_assignment(db, seed):
    _open(db, seed, dt.date(2026, 10, 1))
    data = {"asset": str(seed["asset"].id), "person": str(seed["person_b"].id), "borrowed_at": None, "returned_at": None}
    request = DummyRequest(session={"user_id": seed["user"].id}, db=db)
    with pytest.raises(ValueError, match="chưa thu hồi"):
        asyncio.run(AssignmentAdmin().on_model_change(data, Assignment(), True, request))


def test_panel_history_shows_unknown_start_date(admin_client, db, seed):  # noqa: F811
    html = admin_client.get("/admin/so-tong").text
    assert "(item.borrowed_at || TEXT.unknownDate)" in html
