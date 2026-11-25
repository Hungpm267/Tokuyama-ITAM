"""Nhật ký: giờ hiển thị theo giờ Việt Nam (UTC+7), không còn cột địa chỉ IP."""

from __future__ import annotations

import datetime as dt

import pytest

from app.enums import AuditAction
from app.models import AuditLog
from tests.test_so_tong_edit import admin_client, client, override_db  # noqa: F401


@pytest.fixture
def log(db, seed):
    row = AuditLog(
        user_id=seed["user"].id, table_name="users", record_id=seed["user"].id, action=AuditAction.LOGIN,
        created_at=dt.datetime(2026, 11, 25, 2, 58, 53, 820379, tzinfo=dt.timezone.utc), ip_address="10.1.2.3",
    )
    db.add(row)
    db.flush()
    return row


@pytest.mark.parametrize("lang", ["vi", "en", "ja"])
def test_danh_sach_nhat_ky_hien_gio_viet_nam(admin_client, db, log, lang):  # noqa: F811
    admin_client.cookies.set("itam_lang", lang)
    html = admin_client.get("/admin/audit-log/list").text
    assert "2026-11-25 09:58:53" in html
    assert "+00:00" not in html
    assert "10.1.2.3" not in html
    assert "IP" not in html.split("<thead", 1)[1].split("</thead>", 1)[0]


def test_chi_tiet_nhat_ky_hien_gio_viet_nam_khong_ip(admin_client, db, log):  # noqa: F811
    html = admin_client.get(f"/admin/audit-log/details/{log.id}").text
    assert "2026-11-25 09:58:53" in html
    assert "+00:00" not in html
    assert "10.1.2.3" not in html
