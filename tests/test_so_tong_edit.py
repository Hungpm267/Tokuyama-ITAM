"""Sổ tổng giai đoạn 2: sửa ô, cột phần mềm, ô mật khẩu đã che."""

from __future__ import annotations

import datetime as dt

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.admin import invalidate_model_count_cache, invalidate_user_cache
from app.core.clock import today_local
from app.core.security import create_session_token, hash_password
from app.db import get_db
from app.enums import AuditAction, DEFAULT_ROLE_PERMISSIONS, Module, PermissionAction, RoleCode
from app.main import app
from app.models import Asset, AssetTag, AssetTagLink, AuditLog, PersonSecret, Role, RolePermission, User
from app.services.assignment_service import assign_asset
from app.services.ledger_service import build_ledger_rows

PAST = today_local() - dt.timedelta(days=30)
VIEW_MODULES = (Module.ASSETS, Module.PERSONS, Module.ASSIGNMENTS)


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


def _user(db, code, perms, username):
    role = Role(code=code, name_en=code)
    db.add(role)
    db.flush()
    _grant(db, role, perms)
    user = User(username=username, password_hash=hash_password("Passw0rd!xyz"), display_name="V", role_id=role.id)
    db.add(user)
    db.flush()
    return user


def _viewer(db, username):
    return _user(db, RoleCode.EXECUTIVE.value, {m: [PermissionAction.VIEW] for m in VIEW_MODULES}, username)


def _soft_delete(obj):
    obj.is_deleted = True
    obj.deleted_at = dt.datetime.now(dt.timezone.utc)
    obj.delete_reason = "test"


def _patch(client, row_id, field, value):
    return client.patch("/admin/api/so-tong/cell", json={"id": row_id, "field": field, "value": value})


def _sw(db, code="SW-OFFICE", name="Office"):
    tag = AssetTag(code=code, name_en=name)
    db.add(tag)
    db.flush()
    return tag


def test_edit_asset_serial_is_saved_trimmed_and_audited(admin_client, db, seed):
    res = _patch(admin_client, f"asset-{seed['asset'].id}", "serial", "  NEW-SN  ")
    assert res.status_code == 200, res.text
    assert seed["asset"].serial == "NEW-SN"
    assert seed["asset"].updated_by == seed["user"].id
    assert res.json()["rows"][0]["serial"] == "NEW-SN"
    log = db.scalar(
        select(AuditLog)
        .where(
            AuditLog.table_name == "assets",
            AuditLog.record_id == seed["asset"].id,
            AuditLog.action == AuditAction.UPDATE,
        )
        .order_by(AuditLog.id.desc())
    )
    assert log.before_after["before"]["serial"] == "SN-0001"
    assert log.before_after["after"]["serial"] == "NEW-SN"


def test_edit_rejects_duplicate_serial_ignoring_case(admin_client, db, seed):
    db.add(Asset(device_code="OTHER-SN", serial="OTHER-SN", category_id=seed["cat"].id))
    db.flush()
    res = _patch(admin_client, f"asset-{seed['asset'].id}", "serial", "other-sn")
    assert res.status_code == 400
    assert seed["asset"].serial == "SN-0001"


def test_serial_can_be_cleared_because_device_code_identifies_the_asset(admin_client, db, seed):
    only = Asset(device_code="ONLY-SN", serial="ONLY-SN", category_id=seed["cat"].id)
    db.add(only)
    db.flush()
    assert _patch(admin_client, f"asset-{only.id}", "serial", "").status_code == 200
    assert only.serial is None


def test_edit_clears_optional_field(admin_client, db, seed):
    assert _patch(admin_client, f"asset-{seed['asset'].id}", "serial", "").status_code == 200
    assert seed["asset"].serial is None


def test_edit_person_field_on_holder_row_updates_all_their_rows(admin_client, db, seed):
    second = Asset(device_code="TKY-PC0999", category_id=seed["cat"].id)
    db.add(second)
    db.flush()
    assign_asset(db, seed["asset"].id, seed["person"].id, PAST)
    assign_asset(db, second.id, seed["person"].id, PAST)
    res = _patch(admin_client, f"asset-{seed['asset'].id}", "email", "a@tokuyama.vn")
    assert res.status_code == 200
    assert seed["person"].email == "a@tokuyama.vn"
    rows = res.json()["rows"]
    assert len(rows) == 2 and {r["email"] for r in rows} == {"a@tokuyama.vn"}


def test_edit_person_field_on_machine_without_holder_is_refused(admin_client, db, seed):
    assert _patch(admin_client, f"asset-{seed['asset'].id}", "email", "a@tokuyama.vn").status_code == 400


def test_edit_user_id_rejects_duplicate(admin_client, db, seed):
    seed["person"].user_id = "57959"
    db.flush()
    assert _patch(admin_client, f"person-{seed['person_b'].id}", "user_id", "57959").status_code == 400


def test_edit_department_by_name(admin_client, db, seed):
    row = f"person-{seed['person_b'].id}"
    assert _patch(admin_client, row, "department", "Production").status_code == 200
    assert seed["person_b"].department_id == seed["dept"].id
    assert _patch(admin_client, row, "department", "Khong Co").status_code == 400
    assert _patch(admin_client, row, "department", "").status_code == 200
    assert seed["person_b"].department_id is None


def test_note_goes_to_machine_or_person_depending_on_row(admin_client, db, seed):
    assign_asset(db, seed["asset"].id, seed["person"].id, PAST)
    _patch(admin_client, f"asset-{seed['asset'].id}", "note", "ghi chú máy")
    _patch(admin_client, f"person-{seed['person_b'].id}", "note", "ghi chú người")
    assert seed["asset"].note == "ghi chú máy"
    assert seed["person"].note is None
    assert seed["person_b"].note == "ghi chú người"


@pytest.mark.parametrize(
    "field", ["holder", "asset_status", "person_status", "staff_code", "pc_password"]
)
def test_non_editable_fields_are_refused(admin_client, db, seed, field):
    assert _patch(admin_client, f"asset-{seed['asset'].id}", field, "x").status_code == 400


@pytest.mark.parametrize("row_id", ["asset-abc", "asset-999999", "person-999999", "x-1", 5])
def test_unknown_row_is_refused(admin_client, db, seed, row_id):
    assert _patch(admin_client, row_id, "note", "x").status_code in (400, 404)


def test_overlong_value_is_400_not_500(admin_client, db, seed):
    assert _patch(admin_client, f"asset-{seed['asset'].id}", "serial", "S" * 150).status_code == 400


def test_soft_deleted_row_cannot_be_edited(admin_client, db, seed):
    _soft_delete(seed["asset"])
    db.flush()
    assert _patch(admin_client, f"asset-{seed['asset'].id}", "note", "x").status_code in (400, 404)


def test_edit_needs_change_permission_of_the_right_module(client, db, seed):
    perms = {m: [PermissionAction.VIEW] for m in VIEW_MODULES}
    perms[Module.PERSONS] = [PermissionAction.VIEW, PermissionAction.CHANGE]
    _login(client, _user(db, RoleCode.GA_MANAGER.value, perms, "st_ga"), RoleCode.GA_MANAGER.value)
    assert _patch(client, f"asset-{seed['asset'].id}", "serial", "X").status_code == 403
    assert seed["asset"].serial == "SN-0001"
    assert _patch(client, f"person-{seed['person_b'].id}", "email", "b@tokuyama.vn").status_code == 200


def test_view_only_user_cannot_edit(client, db, seed):
    _login(client, _viewer(db, "st_v3"), RoleCode.EXECUTIVE.value)
    assert _patch(client, f"person-{seed['person_b'].id}", "email", "b@tokuyama.vn").status_code == 403


def test_software_marks_appear_in_rows_and_can_be_replaced(admin_client, db, seed):
    office, pdf = _sw(db), _sw(db, "SW-PDF", "PDF")
    db.add(AssetTagLink(asset_id=seed["asset"].id, tag_id=office.id))
    db.flush()
    rows = build_ledger_rows(db)
    assert next(r for r in rows if r["asset_id"] == seed["asset"].id)["software"] == "Office"
    res = admin_client.put("/admin/api/so-tong/software", json={"asset_id": seed["asset"].id, "codes": ["SW-PDF"]})
    assert res.status_code == 200, res.text
    assert res.json()["rows"][0]["software"] == "PDF"
    links = db.scalars(select(AssetTagLink.tag_id).where(AssetTagLink.asset_id == seed["asset"].id)).all()
    assert links == [pdf.id]


@pytest.mark.parametrize("codes", [["SW-NOPE"], ["ZSCALER"], "SW-PDF"])
def test_software_rejects_unknown_or_non_software_tag(admin_client, db, seed, codes):
    db.add(AssetTag(code="ZSCALER", name_en="Zscaler"))
    db.flush()
    res = admin_client.put("/admin/api/so-tong/software", json={"asset_id": seed["asset"].id, "codes": codes})
    assert res.status_code == 400


def test_non_software_tags_are_kept_when_software_is_replaced(admin_client, db, seed):
    plain = AssetTag(code="ZSCALER", name_en="Zscaler")
    db.add(plain)
    db.flush()
    db.add(AssetTagLink(asset_id=seed["asset"].id, tag_id=plain.id))
    db.flush()
    admin_client.put("/admin/api/so-tong/software", json={"asset_id": seed["asset"].id, "codes": []})
    assert db.scalar(select(AssetTagLink).where(AssetTagLink.tag_id == plain.id)) is not None


def test_secret_flag_only_shows_presence_and_only_with_permission(client, db, seed):
    db.add(PersonSecret(person_id=seed["person"].id, pc_password_enc=b"\x01CIPHERTEXT", key_version=1))
    db.flush()
    with_flag = build_ledger_rows(db, include_secret_flag=True)
    assert next(r for r in with_flag if r["staff_code"] == "TVC00001")["secret_kind"] == "pc"
    without_flag = build_ledger_rows(db)
    assert next(r for r in without_flag if r["staff_code"] == "TVC00001")["secret_kind"] is None
    _login(client, _viewer(db, "st_v4"), RoleCode.EXECUTIVE.value)
    res = client.get("/admin/api/so-tong")
    assert all(r["secret_kind"] is None for r in res.json())
    assert "CIPHERTEXT" not in res.text


def test_page_offers_editing_only_to_those_allowed(client, db, seed):
    _login(client, _viewer(db, "st_v5"), RoleCode.EXECUTIVE.value)
    html = client.get("/admin/so-tong").text
    assert '"assets": false' in html and '"persons": false' in html
    assert "modal-assign-asset" not in html


def test_secret_kind_tells_pc_email_or_both(db, seed):
    from app.models import Person

    people = [Person(full_name=f"Secret {i}", staff_code=f"TVC9000{i}") for i in range(4)]
    db.add_all(people)
    db.flush()
    db.add_all([
        PersonSecret(person_id=people[0].id, pc_password_enc=b"x", key_version=1),
        PersonSecret(person_id=people[1].id, email_password_enc=b"x", key_version=1),
        PersonSecret(person_id=people[2].id, pc_password_enc=b"x", email_password_enc=b"x", key_version=1),
    ])
    db.flush()
    rows = {r["holder"]: r for r in build_ledger_rows(db, include_secret_flag=True)}
    assert [rows[f"Secret {i}"]["secret_kind"] for i in range(4)] == ["pc", "email", "both", "none"]


def test_machine_without_holder_has_no_secret_kind(db, seed):
    row = next(r for r in build_ledger_rows(db, include_secret_flag=True) if r["id"] == f"asset-{seed['asset'].id}")
    assert row["person_id"] is None and row["secret_kind"] is None


def test_edit_device_code_saved_trimmed_and_audited(admin_client, db, seed):
    res = _patch(admin_client, f"asset-{seed['asset'].id}", "device_code", "  TKY-PC0500 ")
    assert res.status_code == 200
    assert seed["asset"].device_code == "TKY-PC0500"
    assert db.query(AuditLog).filter_by(table_name="assets", record_id=seed["asset"].id).count() == 1


def test_device_code_cannot_be_blank(admin_client, db, seed):
    assert _patch(admin_client, f"asset-{seed['asset'].id}", "device_code", "  ").status_code == 400


def test_device_code_duplicate_ignoring_case_is_refused(admin_client, db, seed):
    other = Asset(device_code="TKY-PC0002", category_id=seed["cat"].id)
    db.add(other)
    db.flush()
    assert _patch(admin_client, f"asset-{other.id}", "device_code", "tky-pc0001").status_code == 400


def test_asset_form_refuses_blank_device_code(db, seed):
    import asyncio

    from app.admin import AssetAdmin
    from tests.test_wave4_logic_audit import DummyRequest

    request = DummyRequest(session={"user_id": seed["user"].id}, db=db)
    with pytest.raises(ValueError):
        asyncio.run(AssetAdmin().on_model_change(
            {"device_code": "   ", "status": "IN_STOCK"}, Asset(), True, request
        ))
