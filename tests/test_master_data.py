"""Dọn master data: mã thiết bị, bỏ mã GA và mã phòng ban, ẩn ID, ẩn menu nhãn."""

from __future__ import annotations

import pytest

from tests.test_so_tong_edit import admin_client, client, override_db  # noqa: F401


@pytest.mark.parametrize("path", [
    "/admin/so-tong",
    "/admin/api/so-tong",
    "/admin/asset/list",
    "/admin/person/list",
    "/admin/department/list",
    "/admin/global-search?q=TKY",
    "/admin/trash",
    "/admin/person-secret/list",
])
def test_pages_open_after_cleanup(admin_client, db, seed, path):  # noqa: F811
    assert admin_client.get(path).status_code == 200


def test_asset_detail_page_opens(admin_client, db, seed):  # noqa: F811
    res = admin_client.get(f"/admin/asset/details/{seed['asset'].id}")
    assert res.status_code == 200
    assert "TKY-PC0001" in res.text
    assert "Mã GA" not in res.text


def test_no_view_shows_an_id_column():
    from app.main import app

    admin = app.state.admin
    offenders = []
    for view in admin._views:
        if not hasattr(view, "get_list_columns"):
            continue
        for name in list(view.get_list_columns()) + list(view.get_details_columns()):
            if name == "id":
                offenders.append(view.identity)
    assert offenders == []


def test_sidebar_has_no_asset_tag_link(admin_client, db, seed):  # noqa: F811
    assert "/admin/asset-tag/list" not in admin_client.get("/admin/so-tong").text


def test_audit_trail_shows_device_code_instead_of_number(admin_client, db, seed):  # noqa: F811
    from app.enums import AuditAction
    from app.models import AuditLog

    db.add(AuditLog(table_name="assets", record_id=seed["asset"].id, action=AuditAction.UPDATE,
                    user_id=seed["user"].id, before_after={"before": {"note": "a"}, "after": {"note": "b"}}))
    db.add(AuditLog(table_name="persons", record_id=seed["person"].id, action=AuditAction.UPDATE,
                    user_id=seed["user"].id, before_after={"before": {"note": "a"}, "after": {"note": "b"}}))
    db.flush()
    html = admin_client.get("/admin/audit-log/list").text
    assert "TKY-PC0001" in html
    assert "TVC00001" in html


# --- Kho mật khẩu: giao diện gọn (hướng A) -----------------------------------------


def test_vault_page_is_compact(admin_client, db, seed):  # noqa: F811
    html = admin_client.get("/admin/person-secret/list").text
    assert 'id="vaultSearch"' in html
    for key in ("all", "missing_pc", "missing_email"):
        assert f'data-filter="{key}"' in html
    assert "Kho mật khẩu" in html
    assert "AES-256-GCM" not in html


def test_vault_page_never_contains_ciphertext(admin_client, db, seed):  # noqa: F811
    from app.models import PersonSecret

    db.add(PersonSecret(person_id=seed["person"].id, pc_password_enc=b"\x01CIPHERTEXT", key_version=1))
    db.flush()
    html = admin_client.get("/admin/person-secret/list").text
    assert "CIPHERTEXT" not in html
    assert 'data-action="reveal"' in html


def test_vault_viewer_without_change_right_gets_no_edit_buttons(client, db, seed):  # noqa: F811
    from app.enums import Module, PermissionAction, RoleCode
    from app.models import PersonSecret
    from tests.test_so_tong_edit import _login, _user

    db.add(PersonSecret(person_id=seed["person"].id, pc_password_enc=b"x", key_version=1))
    db.flush()
    viewer = _user(db, RoleCode.EXECUTIVE.value, {Module.SECRETS: [PermissionAction.VIEW]}, "vault_viewer")
    _login(client, viewer, RoleCode.EXECUTIVE.value)
    html = client.get("/admin/person-secret/list").text
    assert 'data-action="edit"' not in html
    assert 'data-action="reveal"' in html


def test_global_search_has_no_ga_wording(admin_client, db, seed):  # noqa: F811
    html = admin_client.get("/admin/global-search?q=TKY").text
    assert "Mã GA" not in html and "Mã Vendor" not in html
    assert html.count("TKY-PC0001") == 1
