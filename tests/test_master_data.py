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
