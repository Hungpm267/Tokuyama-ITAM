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
    ContractAdmin,
    LicenseAssignmentAdmin,
    PersonAdmin,
    invalidate_model_count_cache,
    invalidate_user_cache,
)
from app.core.security import create_session_token, hash_password
from app.db import get_db
from app.enums import (
    AssetStatus,
    ContractItemKind,
    DEFAULT_ROLE_PERMISSIONS,
    DeliveryStatus,
    Module,
    PermissionAction,
    PersonStatus,
    RoleCode,
)
from app.main import app
from app.models import (
    AccessCard,
    Asset,
    AssetCategory,
    Assignment,
    CardLoan,
    Contract,
    ContractLine,
    License,
    LicenseAssignment,
    LicenseProduct,
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


def test_person_cannot_resign_while_holding_a_card_or_license(db, seed):
    db.add(CardLoan(card_id=seed["card"].id, person_id=seed["person"].id, borrowed_at=PAST))
    db.add(LicenseAssignment(license_id=seed["license"].id, person_id=seed["person_b"].id, assigned_at=PAST))
    db.flush()
    with pytest.raises(ValueError):
        _run(PersonAdmin().on_model_change({"status": "RESIGNED"}, seed["person"], False, _req(db)))
    with pytest.raises(ValueError):
        _run(PersonAdmin().on_model_change({"status": "RESIGNED"}, seed["person_b"], False, _req(db)))


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


def test_license_assignment_may_have_both_asset_and_person(db, seed):
    data = {
        "license": str(seed["license"].id), "asset": str(seed["asset"].id), "person": str(seed["person"].id),
        "assigned_at": PAST, "removed_at": None,
    }
    _run(LicenseAssignmentAdmin().on_model_change(data, LicenseAssignment(), True, _req(db)))


def test_expired_license_is_still_assignable(db, seed):
    seed["license"].expiry_date = TODAY - dt.timedelta(days=10)
    db.flush()
    data = {"license": str(seed["license"].id), "person": str(seed["person"].id), "assigned_at": PAST, "removed_at": None}
    _run(LicenseAssignmentAdmin().on_model_change(data, LicenseAssignment(), True, _req(db)))


def test_expired_license_is_flagged_in_the_assignment_form_and_list(admin_client, db, seed):
    seed["license"].expiry_date = TODAY - dt.timedelta(days=10)
    db.add(LicenseAssignment(license_id=seed["license"].id, person_id=seed["person"].id, assigned_at=PAST))
    db.flush()
    form = admin_client.get("/admin/license-assignment/create").text
    assert "đã hết hạn" in form
    listing = admin_client.get("/admin/license-assignment/list").text
    assert "Gói đã hết hạn" in listing


def test_valid_license_is_not_flagged(admin_client, db, seed):
    seed["license"].expiry_date = TODAY + dt.timedelta(days=200)
    db.add(LicenseAssignment(license_id=seed["license"].id, person_id=seed["person"].id, assigned_at=PAST))
    db.flush()
    assert "Gói đã hết hạn" not in admin_client.get("/admin/license-assignment/list").text


# ---------------------------------------------------------------------------
# 4. Tiến độ giao hàng của hợp đồng không gõ tay
# ---------------------------------------------------------------------------


def test_contract_form_has_no_delivery_status_field(admin_client, db, seed):
    html = admin_client.get("/admin/contract/create").text
    assert 'name="code"' in html
    assert 'name="delivery_status"' not in html


def test_contract_delivery_status_is_recomputed_on_save(db, seed):
    contract = Contract(code="W6-C1", vendor_name="V", delivery_status=DeliveryStatus.DELIVERED)
    db.add(contract)
    db.flush()
    db.add(ContractLine(contract_id=contract.id, item_type="PC", qty_ordered=2))
    db.flush()
    view = ContractAdmin()
    req = _req(db, user_id=seed["user"].id)
    _run(view.after_model_change({"note": "x"}, contract, False, req))
    assert contract.delivery_status == DeliveryStatus.PENDING


# ---------------------------------------------------------------------------
# 5. Trùng mã không phân biệt chữ hoa-thường
# ---------------------------------------------------------------------------


def test_asset_serial_duplicate_is_case_insensitive(db, seed):
    data = {"serial": "sn-0001", "status": "IN_STOCK"}  # seed có "SN-0001"
    with pytest.raises(ValueError):
        _run(AssetAdmin().on_model_change(data, Asset(), True, _req(db)))


def test_editing_a_record_does_not_collide_with_itself(db, seed):
    data = {"serial": "sn-0001", "asset_code": seed["asset"].asset_code, "status": "IN_STOCK"}
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


def test_batch_receive_duplicate_check_is_case_insensitive(admin_client, db, seed):
    contract = Contract(code="W6-BR", vendor_name="V")
    db.add(contract)
    db.flush()
    line = ContractLine(contract_id=contract.id, item_type="PC", qty_ordered=5)
    db.add(line)
    db.flush()
    res = admin_client.post(
        f"/admin/contract-line/{line.id}/receive",
        json={"category_id": seed["cat"].id, "items": [{"serial": "sn-0001"}]},
    )
    assert res.status_code == 400


def test_restore_conflict_check_is_case_insensitive(admin_client, db, seed):
    dead = Asset(serial="sn-0001", category_id=seed["cat"].id)
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
    db.add(Asset(asset_code="W6-EXPORT-OTHER", category_id=seed["cat"].id))
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


def test_export_never_contains_secret_columns(admin_client, db, seed):
    body = admin_client.get("/admin/user/export/csv").content.decode("utf-8")
    assert "password_hash" not in body
    body = admin_client.get("/admin/license/export/csv").content.decode("utf-8")
    assert "license_key_enc" not in body


# ---------------------------------------------------------------------------
# 7. Nút thao tác theo ma trận quyền
# ---------------------------------------------------------------------------


def test_view_only_user_sees_no_assign_or_receive_buttons(client, db, seed):
    contract = Contract(code="W6-PERM", vendor_name="V")
    db.add(contract)
    db.flush()
    line = ContractLine(contract_id=contract.id, item_type="PC", qty_ordered=5)
    db.add(line)
    db.flush()
    c = _viewer_client(client, db, {Module.ASSETS: VIEW, Module.ASSIGNMENTS: VIEW, Module.CONTRACTS: VIEW, Module.PERSONS: VIEW})
    assets = c.get("/admin/asset/list")
    assert assets.status_code == 200
    assert "openAssignModal(this" not in assets.text
    lines = c.get("/admin/contract-line/list")
    assert lines.status_code == 200
    assert f"/admin/contract-line/{line.id}/receive" not in lines.text


def test_admin_still_sees_assign_and_receive_buttons(admin_client, db, seed):
    contract = Contract(code="W6-PERM2", vendor_name="V")
    db.add(contract)
    db.flush()
    line = ContractLine(contract_id=contract.id, item_type="PC", qty_ordered=5)
    db.add(line)
    db.flush()
    assert "openAssignModal(this" in admin_client.get("/admin/asset/list").text
    assert f"/admin/contract-line/{line.id}/receive" in admin_client.get("/admin/contract-line/list").text


def test_fully_received_line_shows_no_receive_button_on_details(admin_client, db, seed):
    contract = Contract(code="W6-FULL", vendor_name="V")
    db.add(contract)
    db.flush()
    line = ContractLine(contract_id=contract.id, item_type="PC", qty_ordered=1)
    db.add(line)
    db.flush()
    db.add(Asset(asset_code="W6-FULL-A", category_id=seed["cat"].id, contract_line_id=line.id))
    db.flush()
    html = admin_client.get(f"/admin/contract-line/details/{line.id}").text
    assert f"/admin/contract-line/{line.id}/receive" not in html


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


def test_dashboard_alerts_on_per_assignment_expiry(admin_client, db, seed):
    product = LicenseProduct(name="W6 Trend Micro")
    db.add(product)
    db.flush()
    lic = License(product_id=product.id, seats=10)  # gói không có hạn chung
    db.add(lic)
    db.flush()
    db.add(LicenseAssignment(
        license_id=lic.id, asset_id=seed["asset"].id, assigned_at=PAST, expiry_date=TODAY + dt.timedelta(days=5)
    ))
    db.flush()
    html = admin_client.get("/admin/", follow_redirects=True).text
    assert "W6 Trend Micro" in html


def test_dashboard_expiring_count_is_not_capped_at_eight(admin_client, db, seed):
    for i in range(12):
        product = LicenseProduct(name=f"W6-EXP-{i:02d}")
        db.add(product)
        db.flush()
        db.add(License(product_id=product.id, seats=1, expiry_date=TODAY + dt.timedelta(days=10 + i)))
    db.flush()
    html = admin_client.get("/admin/", follow_redirects=True).text
    assert "12 sắp hết hạn" in html


def test_dashboard_does_not_count_long_expired_licenses_as_expiring(admin_client, db, seed):
    product = LicenseProduct(name="W6-OLD")
    db.add(product)
    db.flush()
    db.add(License(product_id=product.id, seats=1, expiry_date=TODAY - dt.timedelta(days=400)))
    db.flush()
    html = admin_client.get("/admin/", follow_redirects=True).text
    assert "1 sắp hết hạn" not in html
    assert "1 đã hết hạn" in html


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


def test_card_number_duplicate_is_case_insensitive(db, seed):
    from app.admin import AccessCardAdmin

    with pytest.raises(ValueError):
        _run(AccessCardAdmin().on_model_change({"card_no": "card-001", "status": "IN_STOCK"}, AccessCard(), True, _req(db)))


def test_asset_status_enum_still_exported_as_plain_text(admin_client, db, seed):
    seed["asset"].status = AssetStatus.REPAIR
    db.flush()
    body = admin_client.get("/admin/asset/export/csv").content.decode("utf-8")
    assert "REPAIR" in body or "Đang sửa chữa" in body


def test_software_line_receive_button_follows_license_permission(client, db, seed):
    contract = Contract(code="W6-SW", vendor_name="V")
    db.add(contract)
    db.flush()
    line = ContractLine(contract_id=contract.id, item_type="Office", qty_ordered=5, item_kind=ContractItemKind.SOFTWARE)
    db.add(line)
    db.flush()
    c = _viewer_client(
        client, db,
        {Module.CONTRACTS: VIEW, Module.LICENSES: [PermissionAction.VIEW, PermissionAction.ADD]},
        code=RoleCode.GA_MANAGER.value, username="w6_sw",
    )
    assert f"/admin/contract-line/{line.id}/receive-software" in c.get("/admin/contract-line/list").text
