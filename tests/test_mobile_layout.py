"""Giao diện điện thoại: có nút mở menu trượt, Sổ tổng có danh sách thẻ."""

from __future__ import annotations

from tests.test_so_tong_edit import admin_client, client, override_db  # noqa: F401


def test_every_page_has_a_mobile_menu_button(admin_client, db, seed):  # noqa: F811
    for path in ("/admin/so-tong", "/admin/asset/list"):
        html = admin_client.get(path).text
        assert 'id="tokuMenuBtn"' in html
        assert 'id="tokuSidebar"' in html
        assert 'id="tokuSidebarBackdrop"' in html


def test_ledger_has_a_card_list_for_phones(admin_client, db, seed):  # noqa: F811
    html = admin_client.get("/admin/so-tong").text
    assert 'id="stCards"' in html
    assert "renderCards" in html
