"""Kiểm thử Đợt 6: các quyết định nghiệp vụ người dùng đã chốt ngày 10/10/2026.

1. Nhân sự chỉ chuyển sang "đã nghỉ" sau khi đã thu hồi hết máy / thẻ / license.
2. Một lượt gán license được phép vừa có máy vừa có người (giữ nguyên).
3. License hết hạn vẫn gán được nhưng phải có cảnh báo.
4. Tiến độ giao hàng của hợp đồng luôn được tính, không gõ tay.
5. Mã trùng nhau chỉ khác chữ hoa-thường được coi là trùng.
6. Nút Export xuất đúng các cột của danh sách, theo bộ lọc đang chọn, mở được bằng Excel.
7. Nút thao tác hiện theo ma trận quyền, không theo tên vai trò.
8. Cảnh báo license sắp hết hạn tính cả hạn riêng từng lượt gán; số đếm không bị giới hạn 8.
9. Không tạo loại tài sản mang nghĩa phần mềm / license.
"""

from __future__ import annotations

import asyncio
import datetime as dt

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.admin import (
    AssetAdmin,
    AssetCategoryAdmin,
    PersonAdmin,
    invalidate_model_count_cache,
    invalidate_user_cache,
)
from app.core.security import create_session_token, hash_password
from app.db import get_db
from app.enums import (
    AssetStatus,
    DEFAULT_ROLE_PERMISSIONS,
    Module,
    PermissionAction,
    PersonStatus,
    RoleCode,
)
from app.main import app
from app.models import (
    Asset,
    AssetCategory,
    Assignment,
    Person,
    Role,
    RolePermission,
    User,
)
from app.services.assignment_service import assign_asset

TODAY = dt.date.today()
PAST = TODAY - dt.timedelta(days=30)


class DummyRequest:
    def __init__(self, session=None, db=None, query_params=None):
        self.session = session or {}
        self.state = type("State", (), {"db": db})()
        self.query_params = query_params or {}
        self.client = type("Client", (), {"host": "127.0.0.1"})()
        self.cookies = {}


def _req(db, **session):
    return DummyRequest(session={"lang": "vi", **session}, db=db)


def _run(coro):
    return asyncio.run(coro)


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
    invalidate_model_count_cache()
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


def _viewer_client(client, db, perms, code=RoleCode.EXECUTIVE.value, username="w6_viewer"):
    role = Role(code=code, name_en=code)
    db.add(role)
    db.flush()
    _grant(db, role, perms)
    user = User(username=username, password_hash=hash_password("Passw0rd!xyz"), display_name=username, role_id=role.id)
    db.add(user)
    db.flush()
    _login(client, user, code)
    return client


VIEW = [PermissionAction.VIEW]


# ---------------------------------------------------------------------------
# 1. Nghỉ việc: phải thu hồi trước
# ---------------------------------------------------------------------------


def test_person_cannot_resign_while_holding_an_asset(db, seed):
    assign_asset(db, seed["asset"].id, seed["person"].id, PAST)
    with pytest.raises(ValueError) as exc:
        _run(PersonAdmin().on_model_change({"status": "RESIGNED"}, seed["person"], False, _req(db)))
    assert "thu hồi" in str(exc.value).lower()




def test_person_can_resign_once_everything_is_returned(db, seed):
    db.add(Assignment(asset_id=seed["asset"].id, person_id=seed["person"].id, borrowed_at=PAST, returned_at=PAST))
    db.flush()
    _run(PersonAdmin().on_model_change({"status": "RESIGNED"}, seed["person"], False, _req(db)))


def test_editing_an_already_resigned_person_is_not_blocked(db, seed):
    """Dữ liệu cũ: người đã nghỉ mà còn giữ máy vẫn phải sửa được hồ sơ (để ghi chú, v.v.)."""
    assign_asset(db, seed["asset"].id, seed["person"].id, PAST)
    seed["person"].status = PersonStatus.RESIGNED
    db.flush()
    _run(PersonAdmin().on_model_change({"status": "RESIGNED", "note": "x"}, seed["person"], False, _req(db)))


# ---------------------------------------------------------------------------
# 2 + 3. Gán license: máy và người cùng lúc; license hết hạn có cảnh báo
# ---------------------------------------------------------------------------










# ---------------------------------------------------------------------------
# 4. Tiến độ giao hàng của hợp đồng không gõ tay
# ---------------------------------------------------------------------------






# ---------------------------------------------------------------------------
# 5. Trùng mã không phân biệt chữ hoa-thường
# ---------------------------------------------------------------------------


def test_asset_serial_duplicate_is_case_insensitive(db, seed):
    data = {"serial": "sn-0001", "status": "IN_STOCK"}  # seed có "SN-0001"
    with pytest.raises(ValueError):
        _run(AssetAdmin().on_model_change(data, Asset(), True, _req(db)))


def test_editing_a_record_does_not_collide_with_itself(db, seed):
    data = {"serial": "sn-0001", "device_code": seed["asset"].device_code, "status": "IN_STOCK"}
    _run(AssetAdmin().on_model_change(data, seed["asset"], False, _req(db)))


def test_soft_deleted_duplicate_does_not_block_reuse(db, seed):
    seed["asset"].is_deleted = True
    seed["asset"].deleted_at = dt.datetime.now(dt.timezone.utc)
    seed["asset"].delete_reason = "x"
    db.flush()
    _run(AssetAdmin().on_model_change({"serial": "sn-0001", "status": "IN_STOCK"}, Asset(), True, _req(db)))


def test_staff_code_and_category_name_duplicates_are_case_insensitive(db, seed):
    with pytest.raises(ValueError):
        _run(PersonAdmin().on_model_change(
            {"staff_code": "tvc00001", "full_name": "X", "status": "ACTIVE"}, Person(), True, _req(db)))
    with pytest.raises(ValueError):
        _run(AssetCategoryAdmin().on_model_change({"name_en": "LAPTOP"}, AssetCategory(), True, _req(db)))




def test_restore_conflict_check_is_case_insensitive(admin_client, db, seed):
    dead = Asset(device_code="sn-0001", serial="sn-0001", category_id=seed["cat"].id)
    dead.is_deleted = True
    dead.deleted_at = dt.datetime.now(dt.timezone.utc)
    dead.delete_reason = "x"
    db.add(dead)
    db.flush()
    res = admin_client.post("/admin/trash/restore", data={"entity_type": "asset", "item_id": dead.id})
    assert res.status_code == 400
    assert dead.is_deleted is True


# ---------------------------------------------------------------------------
# 6. Export
# ---------------------------------------------------------------------------


def test_asset_export_has_list_columns_and_opens_in_excel(admin_client, db, seed):
    assign_asset(db, seed["asset"].id, seed["person"].id, PAST)
    db.flush()
    res = admin_client.get("/admin/asset/export/csv")
    assert res.status_code == 200
    body = res.content.decode("utf-8")
    assert body.startswith("﻿")
    header = body.splitlines()[0]
    from app.core.i18n import get_property_label

    assert get_property_label(AssetAdmin(), "current_holder", "vi") in header
    assert "is_deleted" not in header and "delete_reason" not in header and "assignments" not in header
    assert "Nguyen Van A" in body
    assert "object at 0x" not in body
    assert "<span" not in body and "<button" not in body


def test_export_follows_the_search_box(admin_client, db, seed):
    db.add(Asset(device_code="W6-EXPORT-OTHER", category_id=seed["cat"].id))
    db.flush()
    body = admin_client.get("/admin/asset/export/csv?search=W6-EXPORT-OTHER").content.decode("utf-8")
    assert "W6-EXPORT-OTHER" in body
    assert "TVC-E00027" not in body


def test_export_neutralises_spreadsheet_formulas(admin_client, db, seed):
    seed["asset"].model = "=HYPERLINK(\"http://evil\",\"x\")"
    db.flush()
    body = admin_client.get("/admin/asset/export/csv").content.decode("utf-8")
    assert "'=HYPERLINK" in body


def test_only_csv_export_is_offered_and_link_keeps_filters(admin_client, db, seed):
    html = admin_client.get("/admin/asset/list?search=TVC").text
    assert "/admin/asset/export/csv?search=TVC" in html
    assert "/admin/asset/export/json" not in html




# ---------------------------------------------------------------------------
# 7. Nút thao tác theo ma trận quyền
# ---------------------------------------------------------------------------








def test_trash_menu_follows_permission_not_username(client, db, seed):
    c = _viewer_client(client, db, {Module.ASSETS: VIEW, Module.TRASH: VIEW}, username="w6_trash")
    assert 'href="/admin/trash"' in c.get("/admin/asset/list").text


def test_trash_menu_hidden_without_permission(client, db, seed):
    c = _viewer_client(client, db, {Module.ASSETS: VIEW}, username="it.admin2")
    assert 'href="/admin/trash"' not in c.get("/admin/asset/list").text


def test_password_vault_link_follows_secrets_permission(client, db, seed):
    c = _viewer_client(client, db, {Module.PERSONS: VIEW}, username="w6_persons")
    assert "/admin/person-secret/list" not in c.get(f"/admin/person/details/{seed['person'].id}").text


# ---------------------------------------------------------------------------
# 8. Cảnh báo license trên dashboard
# ---------------------------------------------------------------------------








# ---------------------------------------------------------------------------
# 9. Loại tài sản không được là phần mềm / license
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["License", "PDF license", "Software", "Phần mềm", "Bản quyền Office", "ライセンス"])
def test_software_like_asset_category_is_rejected(db, seed, name):
    with pytest.raises(ValueError) as exc:
        _run(AssetCategoryAdmin().on_model_change({"name_en": name}, AssetCategory(), True, _req(db)))
    assert "License" in str(exc.value) or "phần mềm" in str(exc.value).lower()


def test_ordinary_asset_category_is_accepted(db, seed):
    _run(AssetCategoryAdmin().on_model_change({"name_en": "Monitor"}, AssetCategory(), True, _req(db)))




def test_asset_status_enum_still_exported_as_plain_text(admin_client, db, seed):
    seed["asset"].status = AssetStatus.REPAIR
    db.flush()
    body = admin_client.get("/admin/asset/export/csv").content.decode("utf-8")
    assert "REPAIR" in body or "Đang sửa chữa" in body


def test_view_only_user_sees_no_assign_button(client, db, seed):
    c = _viewer_client(client, db, {Module.ASSETS: VIEW, Module.ASSIGNMENTS: VIEW, Module.PERSONS: VIEW})
    assets = c.get("/admin/asset/list")
    assert assets.status_code == 200
    assert "openAssignModal(this" not in assets.text


def test_export_never_contains_secret_columns(admin_client, db, seed):
    body = admin_client.get("/admin/user/export/csv").content.decode("utf-8")
    assert "password_hash" not in body
