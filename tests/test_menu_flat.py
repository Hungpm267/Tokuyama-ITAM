"""Menu phẳng, tên dễ hiểu; trang lịch sử bàn giao không dẫn tới form tạo."""

from __future__ import annotations

import re

from app.admin import (
    AssetAdmin, AssetCategoryAdmin, AssignmentAdmin, AuditLogAdmin, PersonAdmin, PersonSecretAdmin,
    RoleAdmin, UserAdmin,
)
from tests.test_so_tong_edit import admin_client, client, override_db  # noqa: F401


def test_muc_hang_ngay_nam_ngay_tren_menu_cai_dat_gom_mot_nhom():
    for view in (PersonAdmin, AssetAdmin, AssignmentAdmin, PersonSecretAdmin, AuditLogAdmin):
        assert view.category is None, view.__name__
    for view in (UserAdmin, RoleAdmin, AssetCategoryAdmin):
        assert view.category == "Cài đặt", view.__name__
    assert AssignmentAdmin.can_create is False and AssignmentAdmin.can_edit is False


def _menu_titles(html: str) -> list[str]:
    nav = html.split('id="navbar-menu"', 1)[1].split("</ul>", 1)[0]
    return [t.strip() for t in re.findall(r'class="nav-link-title[^"]*"[^>]*>\s*([^<]+?)\s*<', nav)]


def test_menu_tieng_viet(admin_client, db, seed):  # noqa: F811
    titles = _menu_titles(admin_client.get("/admin/asset/list").text)
    for name in ("Sổ tổng", "Nhân sự", "Thiết bị", "Lịch sử bàn giao", "Kho mật khẩu", "Nhật ký thay đổi",
                 "Cài đặt", "Tìm kiếm", "Thùng rác"):
        assert name in titles, (name, titles)
    assert not any("Audit" in t or "Danh mục" in t for t in titles), titles


def test_menu_tieng_anh(admin_client, db, seed):  # noqa: F811
    admin_client.cookies.set("itam_lang", "en")
    titles = _menu_titles(admin_client.get("/admin/asset/list").text)
    for name in ("Personnel", "Devices", "Hand-over history", "Password vault", "Change log", "Settings"):
        assert name in titles, (name, titles)


def test_trang_chi_tiet_nhan_su_khong_dan_toi_form_tao_ban_giao(admin_client, db, seed):  # noqa: F811
    html = admin_client.get(f"/admin/person/details/{seed['person'].id}").text
    assert "/admin/assignment/create" not in html
