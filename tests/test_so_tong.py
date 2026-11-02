"""Sổ tổng dạng bảng tính (thiết kế: docs/superpowers/specs/2026-11-02-so-tong-design.md)."""

from __future__ import annotations

import datetime as dt
import json
import re

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.admin import invalidate_model_count_cache, invalidate_user_cache
from app.core.clock import today_local
from app.core.security import create_session_token, hash_password
from app.db import get_db
from app.enums import AssetStatus, DEFAULT_ROLE_PERMISSIONS, Module, PermissionAction, PersonStatus, RoleCode
from app.main import app
from app.models import Asset, PersonSecret, Role, RolePermission, User
from app.services.assignment_service import assign_asset, return_asset
from app.services.ledger_service import build_ledger_rows

PAST = today_local() - dt.timedelta(days=30)


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def override_db(db: Session, monkeypatch):
    class _MockSessionMaker:
        class_ = Session

        def __call__(self, *args, **kwargs):
            return self

        def __enter__(self):
            return db

        def __exit__(self, exc_type, exc_val, exc_tb):
            pass

    mock_maker = _MockSessionMaker()
    app.dependency_overrides[get_db] = lambda: db
    monkeypatch.setattr("app.admin.SessionLocal", mock_maker)
    admin = getattr(app.state, "admin", None)
    if admin:
        monkeypatch.setattr(admin, "session_maker", mock_maker)
        for view in admin._views:
            monkeypatch.setattr(view, "session_maker", mock_maker)
    invalidate_model_count_cache()
    invalidate_user_cache()
    yield
    app.dependency_overrides.clear()
    invalidate_user_cache()


def _grant(db, role, perms):
    for mod, acts in perms.items():
        for act in acts:
            db.add(RolePermission(role_id=role.id, module=mod.value, action=act.value))
    db.flush()


def _login(client, user, role_code):
    client.cookies.set(
        "itam_session",
        create_session_token({"user_id": user.id, "username": user.username, "role": role_code}),
    )
    client.cookies.set("itam_lang", "vi")


@pytest.fixture
def admin_client(client, db, seed):
    _grant(db, seed["role"], DEFAULT_ROLE_PERMISSIONS[RoleCode.ADMIN])
    _login(client, seed["user"], RoleCode.ADMIN.value)
    return client


def _viewer(db, modules, username):
    role = Role(code=RoleCode.EXECUTIVE.value, name_en="Executive")
    db.add(role)
    db.flush()
    _grant(db, role, {m: [PermissionAction.VIEW] for m in modules})
    user = User(username=username, password_hash=hash_password("Passw0rd!xyz"), display_name="V", role_id=role.id)
    db.add(user)
    db.flush()
    return user


def _soft_delete(obj):
    obj.is_deleted = True
    obj.deleted_at = dt.datetime.now(dt.timezone.utc)
    obj.delete_reason = "test"


def _row(rows, **match):
    found = [r for r in rows if all(r.get(k) == v for k, v in match.items())]
    assert len(found) == 1, (match, rows)
    return found[0]


def test_assigned_asset_row_joins_machine_and_holder(db, seed):
    seed["asset"].note = "ghi chú"
    seed["person"].email = "a@tokuyama.vn"
    seed["person"].user_login_id = "57959"
    assign_asset(db, seed["asset"].id, seed["person"].id, PAST)
    row = _row(build_ledger_rows(db), pc_name=seed["asset"].vendor_code)
    assert row["serial"] == "SN-0001"
    assert row["asset_code"] == "TVC-E00027"
    assert row["asset_status"] == "IN_USE"
    assert row["holder"] == "Nguyen Van A"
    assert row["staff_code"] == "TVC00001"
    assert row["user_id"] == "57959"
    assert row["email"] == "a@tokuyama.vn"
    assert row["department"] == "Production"
    assert row["person_status"] == "ACTIVE"
    assert row["borrowed_at"] == PAST.strftime("%d/%m/%Y")
    assert row["note"] == "ghi chú"


def test_unassigned_asset_has_a_row_without_holder(db, seed):
    row = _row(build_ledger_rows(db), pc_name=seed["asset"].vendor_code)
    assert row["asset_status"] == "IN_STOCK"
    assert row["holder"] is None and row["staff_code"] is None


def test_person_without_machine_has_a_row_without_machine_columns(db, seed):
    row = _row(build_ledger_rows(db), staff_code="TVC00002")
    assert row["holder"] == "Tran Thi B"
    assert row["pc_name"] is None and row["asset_status"] is None


def test_person_holding_two_machines_gets_two_rows_and_no_empty_row(db, seed):
    second = Asset(vendor_code="TKY-PC0999", category_id=seed["cat"].id)
    db.add(second)
    db.flush()
    assign_asset(db, seed["asset"].id, seed["person"].id, PAST)
    assign_asset(db, second.id, seed["person"].id, PAST)
    rows = [r for r in build_ledger_rows(db) if r["staff_code"] == "TVC00001"]
    assert sorted(r["pc_name"] for r in rows) == ["TKY-PC0001", "TKY-PC0999"]


def test_soft_deleted_rows_are_excluded(db, seed):
    _soft_delete(seed["asset"])
    _soft_delete(seed["person_b"])
    db.flush()
    rows = build_ledger_rows(db)
    assert not [r for r in rows if r["pc_name"] == seed["asset"].vendor_code]
    assert not [r for r in rows if r["staff_code"] == "TVC00002"]


def test_closed_assignment_does_not_show_a_holder(db, seed):
    assign_asset(db, seed["asset"].id, seed["person"].id, PAST)
    return_asset(db, seed["asset"].id, today_local())
    row = _row(build_ledger_rows(db), pc_name=seed["asset"].vendor_code)
    assert row["holder"] is None and row["asset_status"] == AssetStatus.IN_STOCK.value


def test_row_kind_marks_resigned_people_and_mes_machines(db, seed):
    seed["person_b"].status = PersonStatus.RESIGNED
    mes = Asset(vendor_code="TKY-PC0060", category_id=seed["cat"].id, note="Người dùng theo file Excel: MES system PC 01")
    db.add(mes)
    db.flush()
    rows = build_ledger_rows(db)
    assert _row(rows, staff_code="TVC00002")["row_kind"] == "resigned"
    assert _row(rows, pc_name="TKY-PC0060")["row_kind"] == "mes"
    assert _row(rows, pc_name=seed["asset"].vendor_code)["row_kind"] == ""


def test_api_returns_rows_and_never_any_secret(admin_client, db, seed):
    db.add(PersonSecret(person_id=seed["person"].id, pc_password_enc=b"\x01CIPHERTEXT", key_version=1))
    db.flush()
    res = admin_client.get("/admin/api/so-tong")
    assert res.status_code == 200
    body = res.json()
    assert len(body) == 3  # 1 máy + 2 nhân viên chưa có máy
    raw = json.dumps(body).lower()
    assert "password" not in raw and "_enc" not in raw and "ciphertext" not in raw


def test_api_requires_login(client, db, seed):
    assert client.get("/admin/api/so-tong").status_code == 401


@pytest.mark.parametrize("missing", [Module.ASSETS, Module.PERSONS, Module.ASSIGNMENTS])
def test_api_and_page_require_all_three_view_permissions(client, db, seed, missing):
    modules = {Module.ASSETS, Module.PERSONS, Module.ASSIGNMENTS} - {missing}
    _login(client, _viewer(db, modules, "st_viewer"), RoleCode.EXECUTIVE.value)
    assert client.get("/admin/api/so-tong").status_code == 403
    assert client.get("/admin/so-tong").status_code == 403


def test_view_only_user_can_open_the_ledger(client, db, seed):
    user = _viewer(db, (Module.ASSETS, Module.PERSONS, Module.ASSIGNMENTS), "st_viewer2")
    _login(client, user, RoleCode.EXECUTIVE.value)
    assert client.get("/admin/api/so-tong").status_code == 200


def test_page_renders_grid_and_menu_link(admin_client, db, seed):
    res = admin_client.get("/admin/so-tong")
    assert res.status_code == 200
    assert 'id="soTongGrid"' in res.text
    assert '<h2 class="page-title">' not in res.text
    assert "/static/vendor/tabulator/tabulator.min.js" in res.text
    assert 'href="/admin/so-tong"' in admin_client.get("/admin/asset/list").text


def test_login_lands_on_the_ledger(client, db, seed):
    seed["user"].password_hash = hash_password("Passw0rd!xyz")
    _grant(db, seed["role"], DEFAULT_ROLE_PERMISSIONS[RoleCode.ADMIN])
    db.flush()
    res = client.post(
        "/admin/login",
        data={"username": seed["user"].username, "password": "Passw0rd!xyz"},
        follow_redirects=False,
    )
    assert res.status_code == 302
    assert res.headers["location"].endswith("/admin/so-tong")


def test_page_sends_anonymous_user_to_login_instead_of_raw_json(client, db, seed):
    res = client.get("/admin/so-tong", follow_redirects=False)
    assert res.status_code == 302
    assert res.headers["location"].endswith("/admin/login")


def test_old_dashboard_and_root_go_to_the_ledger(admin_client, db, seed):
    res = admin_client.get("/admin/", follow_redirects=False)
    assert res.status_code == 302
    assert res.headers["location"].endswith("/admin/so-tong")
    res_root = admin_client.get("/", follow_redirects=False)
    assert res_root.status_code == 303
    assert res_root.headers["location"].endswith("/admin/so-tong")


@pytest.mark.parametrize("path", ["/admin/license/list", "/admin/access-card/list", "/admin/contract/list", "/admin/phone/list", "/admin/export/assets"])
def test_removed_modules_are_gone(admin_client, db, seed, path):
    assert admin_client.get(path).status_code == 404


def test_menu_link_is_well_formed_and_comes_before_the_categories(admin_client, db, seed):
    html = admin_client.get("/admin/so-tong").text
    link = re.search(r'<a class="nav-link[^<>]*href="/admin/so-tong">', html)
    assert link is not None
    assert link.start() < html.index("<!-- Category List -->")
    assert 'href="/admin/so-tong">' not in html[html.index("<!-- Category List -->"):]
