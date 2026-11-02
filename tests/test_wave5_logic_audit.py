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
    DepartmentAdmin,
    RoleAdmin,
    invalidate_model_count_cache,
    invalidate_user_cache,
)
from app.core.i18n import format_datetime_clean
from app.core.security import create_session_token
from app.db import get_db
from app.enums import (
    AssetStatus,
    AuditAction,
    ContractItemKind,
    DEFAULT_ROLE_PERMISSIONS,
    DeliveryStatus,
    RoleCode,
)
from app.main import app
from app.models import (
    AccessCard,
    Asset,
    Assignment,
    AuditLog,
    Contract,
    ContractLine,
    Department,
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








# ---------------------------------------------------------------------------
# 4. License và hạng mục hợp đồng
# ---------------------------------------------------------------------------














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




def test_custom_roles_cannot_be_created_because_they_cannot_log_in():
    assert RoleAdmin().can_create is False






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




@pytest.mark.parametrize("body", [[], {"person_id": "abc"}, {"person_id": True}])
def test_secret_save_rejects_malformed_input(admin_client, db, seed, body):
    res = admin_client.post("/admin/person-secret/save", json=body)
    assert res.status_code == 400




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
