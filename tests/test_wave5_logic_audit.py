"""Kiểm thử Đợt 5: rà soát lại sau khi thêm hạng mục phần mềm.

Trọng tâm: mọi đường nhập liệu còn nhận dữ liệu vô lý (license là thiết bị, lịch sử bị
viết lại, danh mục đang dùng bị xóa...) và các chỗ hiển thị sai so với dữ liệu thật.
"""

from __future__ import annotations

import asyncio
import datetime as dt

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException

from app.admin import (
    AssetAdmin,
    AssetCategoryAdmin,
    AssignmentAdmin,
    AuditLogAdmin,
    CardLoanAdmin,
    ContractLineAdmin,
    DepartmentAdmin,
    LicenseAdmin,
    LicenseAssignmentAdmin,
    LicenseProductAdmin,
    LocationAdmin,
    RoleAdmin,
    RolePermissionAdmin,
    invalidate_model_count_cache,
    invalidate_user_cache,
)
from app.core.i18n import format_datetime_clean
from app.core.security import create_session_token, hash_password
from app.db import get_db
from app.enums import (
    AssetStatus,
    AuditAction,
    ContractItemKind,
    DEFAULT_ROLE_PERMISSIONS,
    DeliveryStatus,
    Module,
    PermissionAction,
    PhoneDeviceType,
    RoleCode,
)
from app.main import app
from app.models import (
    AccessCard,
    Asset,
    Assignment,
    AuditLog,
    CardLoan,
    Contract,
    ContractLine,
    Department,
    LicenseAssignment,
    LicenseProduct,
    Phone,
    Role,
    RolePermission,
    User,
    UserPermissionOverride,
)
from app.services.assignment_service import assign_asset
from app.services.license_service import assign_license, receive_license_for_line

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


def _soft_delete(obj):
    obj.is_deleted = True
    obj.deleted_at = dt.datetime.now(dt.timezone.utc)
    obj.delete_reason = "test"


def _delete_req(db, seed):
    return DummyRequest(session={"user_id": seed["user"].id}, db=db, query_params={"delete_reason": "x"})


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


@pytest.fixture
def admin_client(client, db, seed):
    _grant(db, seed["role"], DEFAULT_ROLE_PERMISSIONS[RoleCode.ADMIN])
    _login(client, seed["user"], RoleCode.ADMIN.value)
    client.cookies.set("itam_lang", "vi")
    return client


def _software_line(db, qty=30, kind=ContractItemKind.SOFTWARE, code="HD-W5"):
    contract = Contract(code=code, vendor_name="V", delivery_status=DeliveryStatus.PENDING)
    db.add(contract)
    db.flush()
    line = ContractLine(contract_id=contract.id, item_type="Item", qty_ordered=qty, item_kind=kind)
    db.add(line)
    db.flush()
    return contract, line


# ---------------------------------------------------------------------------
# 1. Không xóa danh mục / vai trò còn đang được dùng
# ---------------------------------------------------------------------------


def test_category_in_use_cannot_be_deleted(db, seed):
    with pytest.raises(HTTPException) as exc:
        _run(AssetCategoryAdmin().delete_model(_delete_req(db, seed), seed["cat"].id))
    assert exc.value.status_code == 400
    assert seed["cat"].is_deleted is False


def test_unused_category_can_still_be_deleted(db, seed):
    from app.models import AssetCategory

    spare = AssetCategory(name_en="Spare Category")
    db.add(spare)
    db.flush()
    _run(AssetCategoryAdmin().delete_model(_delete_req(db, seed), spare.id))
    assert spare.is_deleted is True


def test_department_in_use_cannot_be_deleted(db, seed):
    with pytest.raises(HTTPException):
        _run(DepartmentAdmin().delete_model(_delete_req(db, seed), seed["dept"].id))
    assert seed["dept"].is_deleted is False


def test_license_product_in_use_cannot_be_deleted(db, seed):
    with pytest.raises(HTTPException):
        _run(LicenseProductAdmin().delete_model(_delete_req(db, seed), seed["product"].id))
    assert seed["product"].is_deleted is False


def test_location_in_use_cannot_be_deleted(db, seed):
    db.add(Phone(device_name="W5-PHONE", device_type=PhoneDeviceType.IP_PHONE, location_id=seed["location"].id))
    db.flush()
    with pytest.raises(HTTPException):
        _run(LocationAdmin().delete_model(_delete_req(db, seed), seed["location"].id))
    assert seed["location"].is_deleted is False


def test_role_with_users_cannot_be_deleted(db, seed):
    role = Role(code=RoleCode.GA_MANAGER.value, name_en="GA")
    db.add(role)
    db.flush()
    db.add(User(username="w5_ga", password_hash="x", display_name="GA", role_id=role.id))
    db.flush()
    with pytest.raises(HTTPException):
        _run(RoleAdmin().delete_model(_delete_req(db, seed), role.id))
    assert role.is_deleted is False


# ---------------------------------------------------------------------------
# 2. Gán license / trạng thái thiết bị
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("status", [AssetStatus.DISPOSED, AssetStatus.LOST])
def test_license_cannot_be_assigned_to_a_disposed_or_lost_asset(db, seed, status):
    seed["asset"].status = status
    db.flush()
    data = {"license": str(seed["license"].id), "asset": str(seed["asset"].id), "assigned_at": PAST, "removed_at": None}
    with pytest.raises(ValueError):
        _run(LicenseAssignmentAdmin().on_model_change(data, LicenseAssignment(), True, _req(db)))
    with pytest.raises(ValueError):
        assign_license(db, seed["license"].id, asset_id=seed["asset"].id, assigned_at=PAST)


def test_license_assignment_expiry_cannot_precede_assignment_date(db, seed):
    data = {
        "license": str(seed["license"].id), "person": str(seed["person"].id),
        "assigned_at": PAST, "expiry_date": PAST - dt.timedelta(days=1), "removed_at": None,
    }
    with pytest.raises(ValueError):
        _run(LicenseAssignmentAdmin().on_model_change(data, LicenseAssignment(), True, _req(db)))


@pytest.mark.parametrize("status", ["DISPOSED", "LOST"])
def test_asset_holding_license_seat_cannot_be_disposed_or_lost(db, seed, status):
    db.add(LicenseAssignment(license_id=seed["license"].id, asset_id=seed["asset"].id, assigned_at=PAST))
    db.flush()
    with pytest.raises(ValueError):
        _run(AssetAdmin().on_model_change({"status": status}, seed["asset"], False, _req(db)))


def test_asset_with_drifted_status_can_still_be_edited_when_status_unchanged(db, seed):
    """Dữ liệu cũ có thể đã lệch (IN_USE không ai giữ). Sửa ghi chú không được bị chặn vì trạng thái không đổi."""
    seed["asset"].status = AssetStatus.IN_USE
    db.flush()
    _run(AssetAdmin().on_model_change({"status": "IN_USE", "note": "x"}, seed["asset"], False, _req(db)))


# ---------------------------------------------------------------------------
# 3. Lịch sử đã đóng không được trỏ sang đối tượng khác (bất biến số 7)
# ---------------------------------------------------------------------------


def test_closed_assignment_cannot_be_repointed(db, seed):
    asgn = Assignment(asset_id=seed["asset"].id, person_id=seed["person"].id, borrowed_at=PAST, returned_at=PAST)
    other = Asset(asset_code="W5-OTHER", category_id=seed["cat"].id)
    db.add_all([asgn, other])
    db.flush()
    base = {"borrowed_at": PAST, "returned_at": PAST}
    with pytest.raises(ValueError):
        _run(AssignmentAdmin().on_model_change(
            {**base, "asset": str(seed["asset"].id), "person": str(seed["person_b"].id)}, asgn, False, _req(db)))
    with pytest.raises(ValueError):
        _run(AssignmentAdmin().on_model_change(
            {**base, "asset": str(other.id), "person": str(seed["person"].id)}, asgn, False, _req(db)))
    # Sửa ghi chú / ngày của dòng đã đóng vẫn được
    _run(AssignmentAdmin().on_model_change(
        {**base, "asset": str(seed["asset"].id), "person": str(seed["person"].id), "note": "đính chính"}, asgn, False, _req(db)))


def test_closed_license_assignment_cannot_be_repointed(db, seed):
    row = LicenseAssignment(
        license_id=seed["license"].id, person_id=seed["person"].id, assigned_at=PAST, removed_at=PAST
    )
    db.add(row)
    db.flush()
    data = {"license": str(seed["license"].id), "person": str(seed["person_b"].id), "assigned_at": PAST, "removed_at": PAST}
    with pytest.raises(ValueError):
        _run(LicenseAssignmentAdmin().on_model_change(data, row, False, _req(db)))


def test_closed_card_loan_cannot_be_repointed(db, seed):
    loan = CardLoan(card_id=seed["card"].id, person_id=seed["person"].id, borrowed_at=PAST, returned_at=PAST)
    other = AccessCard(card_no="W5-CARD")
    db.add_all([loan, other])
    db.flush()
    data = {"card": str(other.id), "person": str(seed["person"].id), "borrowed_at": PAST, "returned_at": PAST}
    with pytest.raises(ValueError):
        _run(CardLoanAdmin().on_model_change(data, loan, False, _req(db)))


def test_card_loan_cannot_have_both_employee_and_external_borrower(db, seed):
    data = {
        "card": str(seed["card"].id), "person": str(seed["person"].id), "external_name": "Mr. Tanaka",
        "borrowed_at": PAST, "returned_at": None,
    }
    with pytest.raises(ValueError):
        _run(CardLoanAdmin().on_model_change(data, CardLoan(), True, _req(db)))


# ---------------------------------------------------------------------------
# 4. License và hạng mục hợp đồng
# ---------------------------------------------------------------------------


def test_license_product_cannot_change_once_assigned(db, seed):
    other = LicenseProduct(name="W5 Other Product")
    db.add(other)
    db.add(LicenseAssignment(license_id=seed["license"].id, person_id=seed["person"].id, assigned_at=PAST, removed_at=PAST))
    db.flush()
    with pytest.raises(ValueError):
        _run(LicenseAdmin().on_model_change({"product": str(other.id), "seats": 13}, seed["license"], False, _req(db)))
    _run(LicenseAdmin().on_model_change({"product": str(seed["product"].id), "seats": 13}, seed["license"], False, _req(db)))


def test_clearing_license_contract_line_also_clears_contract(db, seed):
    contract, line = _software_line(db)
    lic = receive_license_for_line(db, line.id, product_id=seed["product"].id, seats=5)
    assert lic.contract_id == contract.id
    data = {"product": str(seed["product"].id), "seats": 5, "contract_line": None}
    _run(LicenseAdmin().on_model_change(data, lic, False, _req(db)))
    assert "contract_id" in data and data["contract_id"] is None


def test_contract_line_cannot_move_to_another_contract_after_receiving(db, seed):
    contract, line = _software_line(db)
    receive_license_for_line(db, line.id, product_id=seed["product"].id, seats=5)
    other = Contract(code="HD-W5-B", vendor_name="V")
    db.add(other)
    db.flush()
    data = {"contract": str(other.id), "item_kind": "SOFTWARE", "qty_ordered": 30}
    with pytest.raises(ValueError):
        _run(ContractLineAdmin().on_model_change(data, line, False, _req(db)))


def test_restoring_an_asset_cannot_overfill_its_contract_line(admin_client, db, seed):
    _, line = _software_line(db, qty=1, kind=ContractItemKind.HARDWARE, code="HD-W5-HW")
    old = Asset(asset_code="W5-OLD", category_id=seed["cat"].id, contract_line_id=line.id)
    _soft_delete(old)
    db.add_all([old, Asset(asset_code="W5-NEW", category_id=seed["cat"].id, contract_line_id=line.id)])
    db.flush()
    res = admin_client.post("/admin/trash/restore", data={"entity_type": "asset", "item_id": old.id})
    assert res.status_code == 400
    assert old.is_deleted is True


def test_restoring_an_asset_onto_a_software_line_is_refused(admin_client, db, seed):
    _, line = _software_line(db, qty=5, kind=ContractItemKind.HARDWARE, code="HD-W5-KIND")
    old = Asset(asset_code="W5-KIND", category_id=seed["cat"].id, contract_line_id=line.id)
    _soft_delete(old)
    db.add(old)
    db.flush()
    line.item_kind = ContractItemKind.SOFTWARE
    db.flush()
    res = admin_client.post("/admin/trash/restore", data={"entity_type": "asset", "item_id": old.id})
    assert res.status_code == 400
    assert old.is_deleted is True


def test_deleted_contract_line_can_be_restored_from_trash(admin_client, db, seed):
    contract, line = _software_line(db, qty=5, code="HD-W5-LINE")
    _soft_delete(line)
    db.flush()
    page = admin_client.get("/admin/trash?entity=contract_line")
    assert page.status_code == 200
    res = admin_client.post("/admin/trash/restore", data={"entity_type": "contract_line", "item_id": line.id})
    assert res.status_code == 200, res.text
    assert line.is_deleted is False


def test_trash_search_reaches_items_beyond_the_first_50(admin_client, db, seed):
    base = dt.datetime.now(dt.timezone.utc)
    for i in range(55):
        card = AccessCard(card_no=f"W5-TRASH-{i:03d}")
        card.is_deleted = True
        card.deleted_at = base - dt.timedelta(days=i)
        card.delete_reason = "test"
        db.add(card)
    db.flush()
    html = admin_client.get("/admin/trash?entity=card&q=W5-TRASH-054").text
    assert "W5-TRASH-054" in html


# ---------------------------------------------------------------------------
# 5. Form chung: khoảng trắng, người tạo/sửa, quyền, mật khẩu
# ---------------------------------------------------------------------------


def test_whitespace_only_required_text_is_rejected(admin_client, db, seed):
    res = admin_client.post("/admin/department/create", data={"code": "W5", "name_en": "   "})
    assert res.status_code == 400
    assert db.scalar(select(Department).where(Department.code == "W5")) is None


def test_text_is_trimmed_and_audit_columns_are_filled(admin_client, db, seed):
    res = admin_client.post(
        "/admin/department/create", data={"code": "  W5T  ", "name_en": "  Quality  "}, follow_redirects=True
    )
    assert res.status_code == 200
    dept = db.scalar(select(Department).where(Department.code == "W5T"))
    assert dept is not None
    assert dept.name_en == "Quality"
    assert dept.created_by == seed["user"].id
    assert dept.updated_by == seed["user"].id


def test_form_update_audit_records_before_and_after(admin_client, db, seed):
    dept = seed["dept"]
    res = admin_client.post(
        f"/admin/department/edit/{dept.id}", data={"name_en": "Production Renamed"}, follow_redirects=True
    )
    assert res.status_code == 200
    log = db.scalar(
        select(AuditLog)
        .where(AuditLog.table_name == "departments", AuditLog.record_id == dept.id, AuditLog.action == AuditAction.UPDATE)
        .order_by(AuditLog.id.desc())
    )
    assert log is not None
    assert log.before_after["before"]["name_en"] == "Production"
    assert log.before_after["after"]["name_en"] == "Production Renamed"
    assert "name_en" in log.summary


def test_new_user_password_has_minimum_length(admin_client, db, seed):
    res = admin_client.post("/admin/user/create", data={
        "username": "w5_short", "display_name": "S", "role": str(seed["role"].id),
        "preferred_lang": "vi", "is_active": "y", "password": "1",
    })
    assert res.status_code == 400
    assert db.scalar(select(User).where(User.username == "w5_short")) is None


def test_role_permission_rows_are_only_editable_through_the_matrix():
    view = RolePermissionAdmin()
    assert view.can_create is False
    assert view.can_edit is False
    assert view.can_delete is False


def test_custom_roles_cannot_be_created_because_they_cannot_log_in():
    assert RoleAdmin().can_create is False


def test_user_permission_override_can_be_created_from_the_form(admin_client, db, seed):
    page = admin_client.get("/admin/user-permission-override/create")
    assert page.status_code == 200
    assert 'name="user_id"' in page.text
    res = admin_client.post("/admin/user-permission-override/create", data={
        "user_id": str(seed["user"].id), "module": "licenses", "action": "view", "granted": "y",
    }, follow_redirects=True)
    assert res.status_code == 200
    row = db.scalar(select(UserPermissionOverride).where(UserPermissionOverride.user_id == seed["user"].id))
    assert row is not None and row.module == "licenses" and row.granted is True


def test_user_permission_override_rejects_unknown_module(admin_client, db, seed):
    res = admin_client.post("/admin/user-permission-override/create", data={
        "user_id": str(seed["user"].id), "module": "asset", "action": "view", "granted": "y",
    })
    assert res.status_code == 400
    assert db.scalar(select(UserPermissionOverride)) is None


def test_validation_messages_follow_the_language_switcher(admin_client, db, seed):
    admin_client.cookies.set("itam_lang", "en")
    seed["asset"].status = AssetStatus.DISPOSED
    db.flush()
    res = admin_client.post("/admin/assignment/create", data={
        "asset": str(seed["asset"].id), "person": str(seed["person"].id), "borrowed_at": PAST.isoformat(),
    })
    assert res.status_code == 400
    assert "cannot be assigned" in res.text


# ---------------------------------------------------------------------------
# 6. Endpoint JSON: kiểu dữ liệu sai phải là 400, không phải 500 hay bị ép kiểu
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("body", [[], {"person_id": True}, {"person_id": [1]}, {"person_id": "abc"}])
def test_assign_endpoint_rejects_malformed_input(admin_client, db, seed, body):
    res = admin_client.post(f"/admin/assets/{seed['asset'].id}/assign", json=body)
    assert res.status_code == 400
    assert seed["asset"].status == AssetStatus.IN_STOCK


def test_return_endpoint_rejects_non_object_body(admin_client, db, seed):
    assign_asset(db, seed["asset"].id, seed["person"].id, PAST)
    res = admin_client.post(f"/admin/assets/{seed['asset'].id}/return", json=[])
    assert res.status_code == 400


def test_batch_receive_rejects_non_object_body_and_overlong_values(admin_client, db, seed):
    _, line = _software_line(db, qty=5, kind=ContractItemKind.HARDWARE, code="HD-W5-BR")
    assert admin_client.post(f"/admin/contract-line/{line.id}/receive", json=[]).status_code == 400
    res = admin_client.post(
        f"/admin/contract-line/{line.id}/receive",
        json={"category_id": seed["cat"].id, "items": [{"serial": "S" * 150}]},
    )
    assert res.status_code == 400
    res = admin_client.post(
        f"/admin/contract-line/{line.id}/receive",
        json={"category_id": True, "items": [{"serial": "W5-OK"}]},
    )
    assert res.status_code == 400


@pytest.mark.parametrize("body", [[], {"person_id": "abc"}, {"person_id": True}])
def test_secret_save_rejects_malformed_input(admin_client, db, seed, body):
    res = admin_client.post("/admin/person-secret/save", json=body)
    assert res.status_code == 400


def test_software_line_receive_link_does_not_need_asset_permission(client, db, seed):
    role = Role(code=RoleCode.GA_MANAGER.value, name_en="GA")
    db.add(role)
    db.flush()
    _grant(db, role, {Module.LICENSES: [PermissionAction.VIEW, PermissionAction.ADD]})
    user = User(username="w5_lic", password_hash=hash_password("Passw0rd!xyz"), display_name="L", role_id=role.id)
    db.add(user)
    db.flush()
    _, line = _software_line(db, qty=5, code="HD-W5-PERM")
    _login(client, user, RoleCode.GA_MANAGER.value)
    res = client.get(f"/admin/contract-line/{line.id}/receive", follow_redirects=False)
    assert res.status_code == 303


# ---------------------------------------------------------------------------
# 7. Phiên đăng nhập
# ---------------------------------------------------------------------------


def test_prefetch_requests_do_not_renew_the_session_cookie(client, db, seed, monkeypatch):
    """Tải trước khi rê chuột không phải là thao tác; nó còn có thể hồi sinh cookie ngay sau khi đăng xuất."""
    import itsdangerous.timed as timed

    _grant(db, seed["role"], DEFAULT_ROLE_PERMISSIONS[RoleCode.ADMIN])
    start = timed.time.time()
    _login(client, seed["user"], RoleCode.ADMIN.value)
    monkeypatch.setattr(timed.time, "time", lambda: start + 20 * 60)
    res = client.get("/admin/api/persons/search", headers={"Sec-Purpose": "prefetch"})
    assert res.status_code == 200
    assert "itam_session" not in res.headers.get("set-cookie", "")


# ---------------------------------------------------------------------------
# 8. Hiển thị
# ---------------------------------------------------------------------------


def test_datetime_is_shown_in_vietnam_time():
    utc_value = dt.datetime(2026, 10, 10, 23, 30, 0, tzinfo=dt.timezone.utc)
    assert format_datetime_clean(utc_value) == "2026-10-11 06:30:00"


def test_date_only_values_are_shown_without_a_fake_time():
    assert format_datetime_clean(dt.date(2026, 10, 10)) == "2026-10-10"


def test_dashboard_stock_counts_only_assets_in_stock(admin_client, db, seed):
    for i, status in enumerate([AssetStatus.REPAIR, AssetStatus.DISPOSED, AssetStatus.LOST, AssetStatus.IN_STOCK]):
        db.add(Asset(asset_code=f"W5-DASH-{i}", category_id=seed["cat"].id, status=status))
    db.flush()
    html = admin_client.get("/admin/", follow_redirects=True).text
    # seed có 1 máy IN_STOCK + 1 máy IN_STOCK vừa thêm = 2; cách tính cũ (tổng - đang mượn) cho ra 5
    assert "2 thiết bị trong kho" in html


def test_contract_list_search_actually_filters(admin_client, db, seed):
    db.add_all([Contract(code="W5-FIND-ME", vendor_name="V"), Contract(code="W5-OTHER-ONE", vendor_name="V")])
    db.flush()
    html = admin_client.get("/admin/contract/list?search=FIND-ME").text
    assert "W5-FIND-ME" in html
    assert "W5-OTHER-ONE" not in html


def test_contract_line_row_has_no_second_hardcoded_receive_link(admin_client, db, seed):
    _, line = _software_line(db, qty=5, code="HD-W5-LINK")
    html = admin_client.get("/admin/contract-line/list").text
    assert f"/admin/contract-line/{line.id}/receive-software" in html
    assert f'/admin/contract-line/{line.id}/receive"' not in html


def test_audit_log_with_unknown_action_filter_does_not_crash(admin_client, db, seed):
    assert admin_client.get("/admin/audit-log/list?action=not-a-real-action").status_code == 200


def test_restore_audit_is_not_summarised_as_a_deletion(db, seed):
    log = AuditLog(
        action=AuditAction.RESTORE, table_name="assets", record_id=1, user_id=seed["user"].id,
        before_after={"before": {"is_deleted": True, "delete_reason": "nhập sai"}, "after": {"is_deleted": False}},
    )
    db.add(log)
    db.flush()
    assert "Lý do xóa" not in log.summary
    assert "Khôi phục" in log.summary


def test_assignment_count_is_fresh_after_quick_assign(admin_client, db, seed):
    view = AuditLogAdmin()  # chỉ để lấy session_maker đã được thay bằng session test
    from app.admin import AssignmentAdmin as _AssignmentAdmin

    counter = _AssignmentAdmin()
    counter.session_maker = type(
        "M", (), {"__call__": lambda s, *a, **k: s, "__enter__": lambda s: db, "__exit__": lambda s, *a: None}
    )()
    assert view is not None
    before = _run(counter.count(DummyRequest(db=db)))
    res = admin_client.post(f"/admin/assets/{seed['asset'].id}/assign", json={"person_id": seed["person"].id})
    assert res.status_code == 200
    assert _run(counter.count(DummyRequest(db=db))) == before + 1
