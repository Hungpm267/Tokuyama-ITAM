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
