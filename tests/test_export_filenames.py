"""Tên file xuất: TVC_<nội dung>_<năm-tháng-ngày>_<giờphút>.csv theo giờ Việt Nam."""

from __future__ import annotations

import datetime as dt
import re

from app.core.clock import export_stamp
from tests.test_so_tong_edit import admin_client, client, override_db  # noqa: F401


def test_export_stamp_theo_gio_viet_nam():
    # 20:05 UTC ngày 23 là 03:05 sáng ngày 24 ở Việt Nam.
    assert export_stamp(dt.datetime(2026, 11, 23, 20, 5, tzinfo=dt.timezone.utc)) == "2026-11-24_0305"


def test_csv_danh_sach_dat_ten_theo_mau(admin_client, db, seed):  # noqa: F811
    res = admin_client.get("/admin/asset/export/csv")
    assert res.status_code == 200
    assert re.search(r'filename="?TVC_Assets_\d{4}-\d{2}-\d{2}_\d{4}\.csv', res.headers["content-disposition"])


def test_so_tong_xuat_ten_ledger(admin_client, db, seed):  # noqa: F811
    html = admin_client.get("/admin/so-tong").text
    assert "'TVC_IT-Ledger_'" in html
    assert "'so-tong.csv'" not in html


def test_so_tong_xuat_xlsx_that(admin_client, db, seed):  # noqa: F811
    html = admin_client.get("/admin/so-tong").text
    assert "table.download('xlsx'" in html
    assert "table.download('csv'" not in html
    assert "'.xlsx'" in html
    # Thư viện SheetJS chỉ nạp khi bấm xuất, không làm trang chậm đi.
    assert '<script src="/static/vendor/sheetjs/xlsx.full.min.js"' not in html
    assert "/static/vendor/sheetjs/xlsx.full.min.js" in html
    assert admin_client.get("/static/vendor/sheetjs/xlsx.full.min.js").status_code == 200
