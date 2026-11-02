"""Kiểm thử Đợt 4: các lỗi logic / nghiệp vụ phát hiện khi rà soát toàn bộ codebase.

Mỗi test tái hiện một lỗi có thật trên đường đi mà người dùng thao tác được
(form SQLAdmin, API modal, thùng rác, dashboard), không chỉ ở tầng service.
"""

from __future__ import annotations

import asyncio
import datetime as dt

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.admin import (
    AssetAdmin,
    AssignmentAdmin,
    AuditLogAdmin,
    RoleAdmin,
    UserAdmin,
    humanize_error_str,
    invalidate_model_count_cache,
)
from app.core.audit import audit_reveal
from app.core.security import create_session_token, hash_password
from app.db import get_db
from app.enums import (
    AssetStatus,
    AuditAction,
    DEFAULT_ROLE_PERMISSIONS,
    Module,
    PermissionAction,
    PersonStatus,
    RoleCode,
)
from app.main import app
from app.models import (
    Asset,
    Assignment,
    AuditLog,
    Person,
    Role,
    RolePermission,
    User,
)
from app.services.assignment_service import assign_asset, return_asset

TODAY = dt.date.today()
PAST = TODAY - dt.timedelta(days=30)
FUTURE = TODAY + dt.timedelta(days=30)


class DummyRequest:
    """Request giả cho các hook SQLAdmin (session, state.db, query_params)."""

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


def _soft_delete(obj, reason="test"):
    obj.is_deleted = True
    obj.deleted_at = dt.datetime.now(dt.timezone.utc)
    obj.delete_reason = reason


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
    yield
    app.dependency_overrides.clear()
    invalidate_model_count_cache()


def _grant(db: Session, role: Role, perms: dict) -> None:
    for mod, acts in perms.items():
        for act in acts:
            exists = db.scalar(
                select(RolePermission).where(
                    RolePermission.role_id == role.id,
                    RolePermission.module == mod.value,
                    RolePermission.action == act.value,
                )
            )
            if not exists:
                db.add(RolePermission(role_id=role.id, module=mod.value, action=act.value))
    db.flush()


def _login(client: TestClient, user: User, role_code: str) -> None:
    token = create_session_token({"user_id": user.id, "username": user.username, "role": role_code})
    client.cookies.set("itam_session", token)


@pytest.fixture
def admin_client(client: TestClient, db: Session, seed) -> TestClient:
    _grant(db, seed["role"], DEFAULT_ROLE_PERMISSIONS[RoleCode.ADMIN])
    _login(client, seed["user"], RoleCode.ADMIN.value)
    return client


def _user_with_role(db: Session, code: str, perms: dict, username: str) -> User:
    role = Role(code=code, name_en=code)
    db.add(role)
    db.flush()
    _grant(db, role, perms)
    user = User(
        username=username,
        password_hash=hash_password("Passw0rd!xyz"),
        display_name=username,
        role_id=role.id,
    )
    db.add(user)
    db.flush()
    return user


# ---------------------------------------------------------------------------
# 1. Múi giờ: "hôm nay" phải tính theo giờ Việt Nam, không theo giờ máy chủ
# ---------------------------------------------------------------------------


def test_today_local_uses_vietnam_time_not_utc():
    from app.core.clock import today_local

    late_utc = dt.datetime(2026, 10, 10, 23, 30, tzinfo=dt.timezone.utc)
    assert today_local(late_utc) == dt.date(2026, 10, 11)


def test_assign_accepts_vietnam_today_when_server_clock_is_utc(db, seed, monkeypatch):
    """06:30 sáng 11/10 giờ VN = 23:30 ngày 10/10 UTC: ngày 11/10 KHÔNG phải tương lai."""
    import app.core.clock as clock

    monkeypatch.setattr(
        clock, "_now_utc", lambda: dt.datetime(2026, 10, 10, 23, 30, tzinfo=dt.timezone.utc)
    )
    asgn = assign_asset(db, seed["asset"].id, seed["person"].id, dt.date(2026, 10, 11))
    assert asgn.borrowed_at == dt.date(2026, 10, 11)


# ---------------------------------------------------------------------------
# 3. Form "Bàn giao thiết bị" của SQLAdmin phải theo đúng luật của service
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("status", [AssetStatus.DISPOSED, AssetStatus.LOST, AssetStatus.REPAIR])
def test_assignment_form_rejects_non_loanable_asset(db, seed, status):
    seed["asset"].status = status
    db.flush()
    data = {"asset": str(seed["asset"].id), "person": str(seed["person"].id), "borrowed_at": PAST, "returned_at": None}
    with pytest.raises(ValueError):
        _run(AssignmentAdmin().on_model_change(data, Assignment(), True, _req(db)))


def test_assignment_form_rejects_resigned_person(db, seed):
    seed["person"].status = PersonStatus.RESIGNED
    db.flush()
    data = {"asset": str(seed["asset"].id), "person": str(seed["person"].id), "borrowed_at": PAST, "returned_at": None}
    with pytest.raises(ValueError):
        _run(AssignmentAdmin().on_model_change(data, Assignment(), True, _req(db)))


def test_assignment_form_rejects_soft_deleted_asset(db, seed):
    _soft_delete(seed["asset"])
    db.flush()
    data = {"asset": str(seed["asset"].id), "person": str(seed["person"].id), "borrowed_at": PAST, "returned_at": None}
    with pytest.raises(ValueError):
        _run(AssignmentAdmin().on_model_change(data, Assignment(), True, _req(db)))


def test_assignment_form_still_allows_closing_an_open_loan(db, seed):
    """Người đã nghỉ việc vẫn phải thu hồi được máy: chỉ chặn khi lượt mượn còn MỞ."""
    asgn = assign_asset(db, seed["asset"].id, seed["person"].id, PAST)
    seed["person"].status = PersonStatus.RESIGNED
    db.flush()
    data = {"asset": str(seed["asset"].id), "person": str(seed["person"].id), "borrowed_at": PAST, "returned_at": TODAY}
    _run(AssignmentAdmin().on_model_change(data, asgn, False, _req(db)))


def test_assignment_form_changing_asset_releases_the_old_asset(db, seed):
    asset_a = seed["asset"]
    asset_b = Asset(asset_code="TVC-E00099", category_id=seed["cat"].id)
    db.add(asset_b)
    db.flush()
    asgn = assign_asset(db, asset_a.id, seed["person"].id, PAST)
    db.flush()

    view = AssignmentAdmin()
    req = _req(db, user_id=seed["user"].id)
    data = {"asset": str(asset_b.id), "person": str(seed["person"].id), "borrowed_at": PAST, "returned_at": None}
    _run(view.on_model_change(data, asgn, False, req))
    asgn.asset_id = asset_b.id
    db.flush()
    _run(view.after_model_change(data, asgn, False, req))

    assert asset_b.status == AssetStatus.IN_USE
    assert asset_a.status == AssetStatus.IN_STOCK


# ---------------------------------------------------------------------------
# 4. Form "Tài sản": trạng thái không được lệch với lượt bàn giao
# ---------------------------------------------------------------------------


def test_asset_form_cannot_leave_in_use_while_on_loan(db, seed):
    assign_asset(db, seed["asset"].id, seed["person"].id, PAST)
    with pytest.raises(ValueError):
        _run(AssetAdmin().on_model_change({"status": "IN_STOCK"}, seed["asset"], False, _req(db)))


def test_asset_form_cannot_set_in_use_without_assignment(db, seed):
    with pytest.raises(ValueError):
        _run(AssetAdmin().on_model_change({"status": "IN_USE"}, seed["asset"], False, _req(db)))
    with pytest.raises(ValueError):
        _run(AssetAdmin().on_model_change({"asset_code": "NEW-1", "status": "IN_USE"}, Asset(), True, _req(db)))


def test_asset_form_allows_normal_status_change(db, seed):
    _run(AssetAdmin().on_model_change({"status": "REPAIR"}, seed["asset"], False, _req(db)))


# ---------------------------------------------------------------------------
# 5. Thu hồi thiết bị: không âm thầm đổi trạng thái người dùng chọn
# ---------------------------------------------------------------------------


def test_return_asset_rejects_unsupported_status_instead_of_coercing(db, seed):
    assign_asset(db, seed["asset"].id, seed["person"].id, PAST)
    with pytest.raises(ValueError):
        return_asset(db, seed["asset"].id, TODAY, return_status=AssetStatus.LOST)
    assert seed["asset"].status == AssetStatus.IN_USE


def test_return_api_rejects_garbage_status(admin_client, db, seed):
    admin_client.post(f"/admin/assets/{seed['asset'].id}/assign", json={"person_id": seed["person"].id})
    res = admin_client.post(f"/admin/assets/{seed['asset'].id}/return", json={"return_status": "banana"})
    assert res.status_code == 400
    assert seed["asset"].status == AssetStatus.IN_USE


def test_return_api_reports_the_status_actually_stored(admin_client, db, seed):
    admin_client.post(f"/admin/assets/{seed['asset'].id}/assign", json={"person_id": seed["person"].id})
    res = admin_client.post(f"/admin/assets/{seed['asset'].id}/return", json={"return_status": "LOST"})
    assert res.status_code == 400
    assert seed["asset"].status == AssetStatus.IN_USE
    res_ok = admin_client.post(f"/admin/assets/{seed['asset'].id}/return", json={"return_status": "REPAIR"})
    assert res_ok.status_code == 200
    assert res_ok.json()["asset_status"] == seed["asset"].status.value == "REPAIR"


def test_person_search_is_not_capped_at_20_for_the_assign_dropdown(admin_client, db, seed):
    for i in range(25):
        db.add(Person(staff_code=f"TVC1{i:04d}", full_name=f"Zz Person {i:02d}", status=PersonStatus.ACTIVE))
    db.flush()
    res = admin_client.get("/admin/api/persons/search")
    assert res.status_code == 200
    assert len(res.json()) >= 26


# ---------------------------------------------------------------------------
# 8. Thùng rác
# ---------------------------------------------------------------------------


def test_restore_asset_with_reused_pc_name_is_a_clean_400(admin_client, db, seed):
    dead = Asset(asset_code="W4-DEAD", pc_name="TKY-PC0001", category_id=seed["cat"].id)
    _soft_delete(dead)
    db.add(dead)
    db.flush()
    res = admin_client.post("/admin/trash/restore", data={"entity_type": "asset", "item_id": dead.id})
    assert res.status_code == 400
    assert "TKY-PC0001" in res.json()["detail"]


def test_restore_person_with_reused_email_is_a_clean_400(admin_client, db, seed):
    seed["person"].email = "a@tokuyama.vn"
    dead = Person(staff_code="TVC09999", full_name="Old", email="a@tokuyama.vn", status=PersonStatus.ACTIVE)
    _soft_delete(dead)
    db.add(dead)
    db.flush()
    res = admin_client.post("/admin/trash/restore", data={"entity_type": "person", "item_id": dead.id})
    assert res.status_code == 400


def test_restore_requires_trash_change_permission(client, db, seed):
    viewer = _user_with_role(db, "TRASH_VIEWER", {Module.TRASH: [PermissionAction.VIEW]}, "trash_viewer")
    _login(client, viewer, "TRASH_VIEWER")
    _soft_delete(seed["person_b"])
    db.flush()
    res = client.post("/admin/trash/restore", data={"entity_type": "person", "item_id": seed["person_b"].id})
    assert res.status_code == 403
    assert seed["person_b"].is_deleted is True


def test_trash_restore_button_does_not_inline_names_into_javascript(admin_client, db, seed):
    seed["person_b"].full_name = "X');alert(1)//"
    _soft_delete(seed["person_b"])
    db.flush()
    html = admin_client.get("/admin/trash?entity=person").text
    assert "X&#39;);alert(1)//&#39;" not in html
    assert "openRestoreModal('person'" not in html


def test_secret_vault_page_does_not_inline_names_into_javascript(admin_client, db, seed):
    from app.models import PersonSecret

    seed["person"].full_name = "x');alert(1);//"
    # Nút "Xem" chỉ hiện khi nhân viên đã có mật khẩu lưu trong kho.
    db.add(PersonSecret(person_id=seed["person"].id, pc_password_enc=b"ciphertext", key_version=1))
    db.flush()
    res = admin_client.get("/admin/person-secret/list")
    assert res.status_code == 200
    html = res.text
    assert "revealSecret(" in html
    assert "'pc_password', '" not in html and "'email_password', '" not in html


# ---------------------------------------------------------------------------
# 9. Lớp SQLAdmin chung
# ---------------------------------------------------------------------------


def test_count_cache_is_not_shared_between_audit_filters(db, seed):
    audit_reveal(db, seed["user"].id, "person_secrets", seed["person"].id, "pc_password")
    for _ in range(3):
        db.add(AuditLog(action=AuditAction.LOGIN, table_name="users", user_id=seed["user"].id))
    db.flush()
    view = AuditLogAdmin()
    view.session_maker = type("M", (), {"__call__": lambda s, *a, **k: s, "__enter__": lambda s: db, "__exit__": lambda s, *a: None})()
    filtered = _run(view.count(DummyRequest(db=db, query_params={"action": "REVEAL"})))
    everything = _run(view.count(DummyRequest(db=db, query_params={})))
    assert filtered == 1
    assert everything >= 4


def test_reveal_audit_summary_names_the_field(db, seed):
    log = audit_reveal(db, seed["user"].id, "person_secrets", seed["person"].id, "pc_password")
    assert "pc_password" in log.summary


def test_duplicate_asset_code_is_not_reported_as_duplicate_serial():
    raw = (
        '(psycopg.errors.UniqueViolation) duplicate key value violates unique constraint "uq_alive_assets_asset_code"\n'
        "DETAIL:  Key (asset_code)=(A1) already exists.\n"
        "[SQL: INSERT INTO assets (asset_code, pc_name, serial, model) VALUES (%(asset_code)s, %(serial)s)]"
    )
    msg = humanize_error_str(raw, lang="vi")
    assert "Mã tài sản" in msg
    assert "Serial" not in msg


def test_duplicate_person_email_is_not_reported_as_duplicate_staff_code():
    raw = (
        '(psycopg.errors.UniqueViolation) duplicate key value violates unique constraint "uq_alive_persons_email"\n'
        "[SQL: INSERT INTO persons (staff_code, full_name, email) VALUES (...)]"
    )
    msg = humanize_error_str(raw, lang="vi")
    assert "Mã nhân viên" not in msg
    assert "Email" in msg


def test_user_form_offers_japanese_as_preferred_language():
    codes = [c[0] for c in UserAdmin.form_args["preferred_lang"]["choices"]]
    assert "ja" in codes


def test_admin_cannot_deactivate_or_demote_own_account(db, seed):
    me = seed["user"]
    req = _req(db, user_id=me.id)
    with pytest.raises(ValueError):
        _run(UserAdmin().on_model_change({"is_active": False, "role": str(me.role_id)}, me, False, req))
    other_role = Role(code="GA_MANAGER", name_en="GA")
    db.add(other_role)
    db.flush()
    with pytest.raises(ValueError):
        _run(UserAdmin().on_model_change({"is_active": True, "role": str(other_role.id)}, me, False, req))


def test_system_role_code_cannot_be_renamed(db, seed):
    with pytest.raises(ValueError):
        _run(RoleAdmin().on_model_change({"code": "IT_ADMIN", "name_en": "x"}, seed["role"], False, _req(db)))


def test_login_page_does_not_redirect_loop_for_deactivated_user(client, db, seed):
    from app.admin import invalidate_user_cache

    seed["user"].is_active = False
    db.flush()
    invalidate_user_cache()
    _login(client, seed["user"], RoleCode.ADMIN.value)
    res = client.get("/admin/login", follow_redirects=False)
    assert res.status_code == 200


def test_session_secret_is_mandatory_in_production():
    from app.core.security import load_session_secret

    with pytest.raises(RuntimeError):
        load_session_secret({"ITAM_ENV": "prod"})
    assert load_session_secret({"ITAM_ENV": "prod", "ITAM_SESSION_SECRET": "s3cret"}) == "s3cret"
    assert load_session_secret({"ITAM_ENV": "dev"})


# ---------------------------------------------------------------------------
# 10. Phiên đăng nhập: 30 phút KHÔNG THAO TÁC, không phải 30 phút kể từ lúc đăng nhập
# ---------------------------------------------------------------------------


def test_session_token_is_renewed_while_user_is_active(client, db, seed, monkeypatch):
    import itsdangerous.timed as timed

    _grant(db, seed["role"], DEFAULT_ROLE_PERMISSIONS[RoleCode.ADMIN])
    real_time = timed.time.time
    start = real_time()
    _login(client, seed["user"], RoleCode.ADMIN.value)

    monkeypatch.setattr(timed.time, "time", lambda: start + 20 * 60)
    res1 = client.get("/admin/api/persons/search")
    assert res1.status_code == 200
    assert "itam_session" in res1.headers.get("set-cookie", "")

    monkeypatch.setattr(timed.time, "time", lambda: start + 40 * 60)
    res2 = client.get("/admin/api/persons/search")
    assert res2.status_code == 200


def test_idle_session_still_expires_after_30_minutes(client, db, seed, monkeypatch):
    import itsdangerous.timed as timed

    _grant(db, seed["role"], DEFAULT_ROLE_PERMISSIONS[RoleCode.ADMIN])
    start = timed.time.time()
    _login(client, seed["user"], RoleCode.ADMIN.value)
    monkeypatch.setattr(timed.time, "time", lambda: start + 31 * 60)
    assert client.get("/admin/api/persons/search").status_code == 401


# ---------------------------------------------------------------------------
# 12. Đi qua form HTTP thật của SQLAdmin (dữ liệu form là chuỗi pk / tên ENUM)
# ---------------------------------------------------------------------------


def test_http_assignment_form_cannot_put_a_disposed_asset_back_in_use(admin_client, db, seed):
    asset = seed["asset"]
    asset.status = AssetStatus.DISPOSED
    db.flush()
    res = admin_client.post("/admin/assignment/create", data={
        "asset": str(asset.id),
        "person": str(seed["person"].id),
        "borrowed_at": PAST.isoformat(),
    })
    assert res.status_code == 400
    assert db.scalar(select(Assignment).where(Assignment.asset_id == asset.id)) is None
    db.refresh(asset)
    assert asset.status == AssetStatus.DISPOSED


def test_http_assignment_form_happy_path_still_works(admin_client, db, seed):
    asset = seed["asset"]
    res = admin_client.post("/admin/assignment/create", data={
        "asset": str(asset.id),
        "person": str(seed["person"].id),
        "borrowed_at": PAST.isoformat(),
    }, follow_redirects=True)
    assert res.status_code == 200
    db.refresh(asset)
    assert asset.status == AssetStatus.IN_USE
    audit = db.scalar(
        select(AuditLog).where(AuditLog.table_name == "assets", AuditLog.record_id == asset.id)
    )
    assert audit is not None


def test_http_asset_form_cannot_mark_a_loaned_asset_in_stock(admin_client, db, seed):
    asset = seed["asset"]
    assign_asset(db, asset.id, seed["person"].id, PAST)
    db.flush()
    res = admin_client.post(f"/admin/asset/edit/{asset.id}", data={
        "asset_code": asset.asset_code,
        "pc_name": asset.pc_name,
        "serial": asset.serial,
        "category": str(seed["cat"].id),
        "status": "IN_STOCK",
    })
    assert res.status_code == 400
    db.refresh(asset)
    assert asset.status == AssetStatus.IN_USE


# ---------------------------------------------------------------------------
# 13. Ô chọn quan hệ trên form không được liệt kê bản ghi đã xóa mềm
# ---------------------------------------------------------------------------


def test_asset_form_does_not_offer_deleted_category(admin_client, db, seed):
    from app.models import AssetCategory

    dead_cat = AssetCategory(name_en="Deleted Category X")
    _soft_delete(dead_cat)
    db.add(dead_cat)
    db.flush()
    res = admin_client.get("/admin/asset/create")
    assert res.status_code == 200
    assert seed["cat"].name_en in res.text
    assert "Deleted Category X" not in res.text


def test_editing_a_row_keeps_its_soft_deleted_category(admin_client, db, seed):
    """Lọc bản ghi đã xóa khỏi ô chọn KHÔNG được làm bản ghi đang sửa bị trỏ sang giá trị khác."""
    from app.models import AssetCategory

    first_cat = seed["cat"]
    old_cat = AssetCategory(name_en="Old Monitor Category")
    db.add(old_cat)
    db.flush()
    asset = Asset(asset_code="W4-KEEP-1", category_id=old_cat.id)
    db.add(asset)
    db.flush()
    _soft_delete(old_cat)
    db.flush()

    page = admin_client.get(f"/admin/asset/edit/{asset.id}")
    assert page.status_code == 200
    assert "Old Monitor Category" in page.text

    res = admin_client.post(f"/admin/asset/edit/{asset.id}", data={
        "asset_code": "W4-KEEP-1",
        "category": str(old_cat.id),
        "status": "IN_STOCK",
        "note": "chỉ sửa ghi chú",
    }, follow_redirects=True)
    assert res.status_code == 200
    db.refresh(asset)
    assert asset.note == "chỉ sửa ghi chú"
    assert asset.category_id == old_cat.id != first_cat.id


def test_editing_closed_history_keeps_its_soft_deleted_person(admin_client, db, seed):
    asset = seed["asset"]
    leaver = Person(staff_code="TVC07777", full_name="Nguoi Cu Da Xoa", status=PersonStatus.ACTIVE)
    db.add(leaver)
    db.flush()
    asgn = Assignment(asset_id=asset.id, person_id=leaver.id, borrowed_at=PAST, returned_at=PAST)
    db.add(asgn)
    db.flush()
    _soft_delete(leaver)
    db.flush()

    page = admin_client.get(f"/admin/assignment/edit/{asgn.id}")
    assert page.status_code == 200
    assert "Nguoi Cu Da Xoa" in page.text

    res = admin_client.post(f"/admin/assignment/edit/{asgn.id}", data={
        "asset": str(asset.id),
        "person": str(leaver.id),
        "borrowed_at": PAST.isoformat(),
        "returned_at": PAST.isoformat(),
        "note": "sửa ghi chú",
    }, follow_redirects=True)
    assert res.status_code == 200
    db.refresh(asgn)
    assert asgn.person_id == leaver.id
    assert asgn.note == "sửa ghi chú"


def test_create_form_still_hides_deleted_rows_referenced_by_other_records(admin_client, db, seed):
    leaver = Person(staff_code="TVC07778", full_name="Khong Duoc Hien", status=PersonStatus.ACTIVE)
    db.add(leaver)
    db.flush()
    db.add(Assignment(asset_id=seed["asset"].id, person_id=leaver.id, borrowed_at=PAST, returned_at=PAST))
    _soft_delete(leaver)
    db.flush()
    assert "Khong Duoc Hien" not in admin_client.get("/admin/assignment/create").text


def test_whitespace_delete_reason_does_not_crash(db, seed):
    req = DummyRequest(session={"user_id": seed["user"].id}, db=db, query_params={"delete_reason": "   "})
    _run(AssetAdmin().delete_model(req, seed["asset"].id))
    assert seed["asset"].is_deleted is True
    assert seed["asset"].delete_reason.strip()


def test_form_dropdowns_hide_soft_deleted_rows(admin_client, db, seed):
    dead_asset = Asset(serial="DEAD-ASSET-SN", category_id=seed["cat"].id)
    live_asset = Asset(serial="LIVE-ASSET-SN", category_id=seed["cat"].id)
    dead_person = Person(staff_code="TVC08888", full_name="Nguoi Da Xoa", status=PersonStatus.ACTIVE)
    _soft_delete(dead_asset)
    _soft_delete(dead_person)
    db.add_all([dead_asset, live_asset, dead_person])
    db.flush()

    res = admin_client.get("/admin/assignment/create")
    assert res.status_code == 200
    assert "LIVE-ASSET-SN" in res.text
    assert "DEAD-ASSET-SN" not in res.text
    assert "Nguoi Da Xoa" not in res.text
