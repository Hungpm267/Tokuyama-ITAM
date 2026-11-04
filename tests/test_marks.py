"""Kiểu đánh dấu màu cho máy trên Sổ tổng (nhãn MARK-)."""

from __future__ import annotations

import asyncio
import re

import pytest

from app.admin import AssetTagAdmin
from app.enums import RoleCode
from app.models import AssetTag, AssetTagLink, AuditLog
from app.services import mark_service
from app.services.ledger_service import build_ledger_rows, set_asset_software
from tests.test_so_tong_edit import _login, _viewer, admin_client, client, override_db  # noqa: F401
from tests.test_wave4_logic_audit import DummyRequest


def _mark(db, name="Máy MES", color="#fef9c3", seed=None):
    return mark_service.create_mark(db, name, color, user_id=seed["user"].id if seed else None, ip_address=None)


def _row(db, seed):
    return next(r for r in build_ledger_rows(db) if r["id"] == f"asset-{seed['asset'].id}")


def _links(db, asset_id):
    return [link.tag_id for link in db.query(AssetTagLink).filter_by(asset_id=asset_id)]


def test_create_mark_generates_code_and_audits(db, seed):
    tag = _mark(db, seed=seed)
    assert re.fullmatch(r"MARK-[A-Z0-9-]+", tag.code) and len(tag.code) <= 30
    assert tag.name_en == "Máy MES" and tag.color == "#fef9c3"
    assert db.query(AuditLog).filter_by(table_name="asset_tags", record_id=tag.id).count() == 1


def test_mark_name_must_be_unique_ignoring_case(db, seed):
    _mark(db, seed=seed)
    with pytest.raises(ValueError):
        _mark(db, name="máy mes", seed=seed)


def test_japanese_name_still_gets_a_code(db, seed):
    assert _mark(db, name="ソフト無し", seed=seed).code.startswith("MARK-")


@pytest.mark.parametrize("color", ["red", "#fff", "#12345g", "", None])
def test_bad_color_is_refused(db, seed, color):
    with pytest.raises(ValueError):
        _mark(db, color=color, seed=seed)


@pytest.mark.parametrize("name", ["", "   ", "x" * 101])
def test_bad_name_is_refused(db, seed, name):
    with pytest.raises(ValueError):
        _mark(db, name=name, seed=seed)


def test_update_mark_changes_name_and_color(db, seed):
    tag = _mark(db, seed=seed)
    mark_service.update_mark(db, tag.id, "MES", "#00ff00", user_id=seed["user"].id, ip_address=None)
    assert (tag.name_en, tag.color) == ("MES", "#00ff00")


def test_asset_has_at_most_one_mark(db, seed):
    software = AssetTag(code="SW-OFFICE", name_en="Office")
    db.add(software)
    db.flush()
    db.add(AssetTagLink(asset_id=seed["asset"].id, tag_id=software.id))
    a, b = _mark(db, "A", "#111111", seed), _mark(db, "B", "#222222", seed)
    aid = seed["asset"].id
    mark_service.set_asset_mark(db, aid, a.id, user_id=None, ip_address=None)
    mark_service.set_asset_mark(db, aid, b.id, user_id=None, ip_address=None)
    assert sorted(_links(db, aid)) == sorted([software.id, b.id])
    mark_service.set_asset_mark(db, aid, None, user_id=None, ip_address=None)
    assert _links(db, aid) == [software.id]


def test_set_asset_software_keeps_mark(db, seed):
    tag = _mark(db, seed=seed)
    mark_service.set_asset_mark(db, seed["asset"].id, tag.id, user_id=None, ip_address=None)
    set_asset_software(db, seed["asset"].id, [])
    assert _links(db, seed["asset"].id) == [tag.id]


def test_delete_mark_unlinks_assets_and_soft_deletes(db, seed):
    from app.models import Asset

    other = Asset(serial="SN-OTHER", category_id=seed["cat"].id)
    db.add(other)
    db.flush()
    tag = _mark(db, seed=seed)
    for asset_id in (seed["asset"].id, other.id):
        mark_service.set_asset_mark(db, asset_id, tag.id, user_id=None, ip_address=None)
    assert mark_service.delete_mark(db, tag.id, user_id=seed["user"].id, ip_address=None) == 2
    assert tag.is_deleted and tag.delete_reason
    assert _links(db, seed["asset"].id) == []
    assert _mark(db, seed=seed).id != tag.id


def test_list_marks_counts_alive_assets(db, seed):
    tag = _mark(db, seed=seed)
    mark_service.set_asset_mark(db, seed["asset"].id, tag.id, user_id=None, ip_address=None)
    assert mark_service.list_marks(db) == [
        {"id": tag.id, "code": tag.code, "name": "Máy MES", "color": "#fef9c3", "count": 1}
    ]


def test_ledger_row_carries_mark(db, seed):
    tag = _mark(db, seed=seed)
    mark_service.set_asset_mark(db, seed["asset"].id, tag.id, user_id=None, ip_address=None)
    assert _row(db, seed)["mark"] == {"id": tag.id, "name": "Máy MES", "color": "#fef9c3"}


def test_mes_note_no_longer_colors_row(db, seed):
    seed["asset"].note = "MES system PC 01"
    db.flush()
    row = _row(db, seed)
    assert row["row_kind"] == "" and row["mark"] is None


def test_mark_name_is_returned_as_plain_text(admin_client, db, seed):  # noqa: F811
    name = "<img src=x onerror=alert(1)>"
    res = admin_client.post("/admin/api/so-tong/marks", json={"name": name, "color": "#123456"})
    assert res.status_code == 200
    assert any(m["name"] == name for m in res.json()["marks"])


def test_api_refuses_bad_color(admin_client, db, seed):  # noqa: F811
    assert admin_client.post("/admin/api/so-tong/marks", json={"name": "X", "color": "red"}).status_code == 400


def test_api_sets_and_clears_mark_on_asset(admin_client, db, seed):  # noqa: F811
    tag = _mark(db, seed=seed)
    res = admin_client.put("/admin/api/so-tong/mark", json={"asset_id": seed["asset"].id, "tag_id": tag.id})
    assert res.status_code == 200
    assert res.json()["rows"][0]["mark"]["id"] == tag.id
    res = admin_client.put("/admin/api/so-tong/mark", json={"asset_id": seed["asset"].id, "tag_id": None})
    assert res.json()["rows"][0]["mark"] is None


def test_api_updates_and_deletes_mark(admin_client, db, seed):  # noqa: F811
    tag = _mark(db, seed=seed)
    res = admin_client.patch(f"/admin/api/so-tong/marks/{tag.id}", json={"name": "MES", "color": "#000000"})
    assert res.status_code == 200 and tag.name_en == "MES"
    assert admin_client.delete(f"/admin/api/so-tong/marks/{tag.id}").status_code == 200
    assert tag.is_deleted


@pytest.mark.parametrize("call", ["post", "patch", "delete", "put"])
def test_view_only_user_cannot_change_marks(client, db, seed, call):  # noqa: F811
    tag = _mark(db, seed=seed)
    _login(client, _viewer(db, f"mark_viewer_{call}"), RoleCode.EXECUTIVE.value)
    res = {
        "post": lambda: client.post("/admin/api/so-tong/marks", json={"name": "Z", "color": "#123456"}),
        "patch": lambda: client.patch(f"/admin/api/so-tong/marks/{tag.id}", json={"name": "Z", "color": "#123456"}),
        "delete": lambda: client.delete(f"/admin/api/so-tong/marks/{tag.id}"),
        "put": lambda: client.put("/admin/api/so-tong/mark", json={"asset_id": seed["asset"].id, "tag_id": tag.id}),
    }[call]()
    assert res.status_code == 403
    assert not tag.is_deleted and tag.name_en == "Máy MES" and _links(db, seed["asset"].id) == []


def test_view_only_user_can_list_marks(client, db, seed):  # noqa: F811
    _mark(db, seed=seed)
    _login(client, _viewer(db, "mark_lister"), RoleCode.EXECUTIVE.value)
    res = client.get("/admin/api/so-tong/marks")
    assert res.status_code == 200 and res.json()[0]["name"] == "Máy MES"


@pytest.mark.parametrize("which", ["software", "deleted"])
def test_cannot_set_mark_with_software_or_deleted_tag(admin_client, db, seed, which):  # noqa: F811
    if which == "software":
        tag = AssetTag(code="SW-VISIO", name_en="Visio")
        db.add(tag)
        db.flush()
    else:
        tag = _mark(db, seed=seed)
        mark_service.delete_mark(db, tag.id, user_id=None, ip_address=None)
    res = admin_client.put("/admin/api/so-tong/mark", json={"asset_id": seed["asset"].id, "tag_id": tag.id})
    assert res.status_code == 400


@pytest.mark.parametrize("old_code,new_code", [("MARK-MES", "SW-MES"), ("SW-VISIO", "MARK-VISIO")])
def test_tag_admin_refuses_switching_between_mark_and_software(db, seed, old_code, new_code):
    tag = AssetTag(code=old_code, name_en="X", color="#123456")
    db.add(tag)
    db.flush()
    request = DummyRequest(session={"user_id": seed["user"].id}, db=db)
    with pytest.raises(ValueError):
        asyncio.run(AssetTagAdmin().on_model_change({"code": new_code, "name_en": "X"}, tag, False, request))


def test_page_has_mark_legend_and_manager(admin_client, db, seed):  # noqa: F811
    html = admin_client.get("/admin/so-tong").text
    assert 'id="stLegend"' in html and 'id="stMarkManager"' in html and "renderLegend" in html
    assert 'id="stMarkManage"' in html
    assert "st-mes" not in html


def test_viewer_sees_legend_without_manage_button(client, db, seed):  # noqa: F811
    _login(client, _viewer(db, "legend_viewer"), RoleCode.EXECUTIVE.value)
    html = client.get("/admin/so-tong").text
    assert 'id="stLegend"' in html
    assert 'id="stMarkManage"' not in html
