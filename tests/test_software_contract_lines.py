"""Hạng mục hợp đồng loại Phần mềm: nhận hàng bằng gói license, đếm theo số seat.

Thiết kế: docs/superpowers/specs/2026-10-10-software-contract-lines-design.md
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
    ContractLineAdmin,
    LicenseAdmin,
    invalidate_model_count_cache,
    invalidate_user_cache,
)
from app.core.security import create_session_token, hash_password
from app.db import get_db
from app.enums import (
    AuditAction,
    ContractItemKind,
    DEFAULT_ROLE_PERMISSIONS,
    DeliveryStatus,
    Module,
    PermissionAction,
    RoleCode,
)
from app.main import app
from app.models import (
    Asset,
    AuditLog,
    Contract,
    ContractLine,
    License,
    Role,
    RolePermission,
    User,
)
from app.services.contract_service import line_received_qty, sync_contract_delivery_status
from app.services.license_service import receive_license_for_line

TODAY = dt.date.today()


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
    return client


def _contract(db, code="HD-SW"):
    contract = Contract(code=code, vendor_name="V", delivery_status=DeliveryStatus.PENDING)
    db.add(contract)
    db.flush()
    return contract


def _line(db, contract, kind=ContractItemKind.SOFTWARE, qty=30, item_type="Office LTSC 2024"):
    line = ContractLine(contract_id=contract.id, item_type=item_type, qty_ordered=qty, item_kind=kind)
    db.add(line)
    db.flush()
    return line


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


def test_existing_style_line_defaults_to_hardware(db, seed):
    contract = _contract(db)
    line = ContractLine(contract_id=contract.id, item_type="Laptop", qty_ordered=2)
    db.add(line)
    db.flush()
    db.refresh(line)
    assert line.item_kind == ContractItemKind.HARDWARE


# ---------------------------------------------------------------------------
# Cách tính "đã nhận"
# ---------------------------------------------------------------------------


def test_software_line_received_is_sum_of_seats(db, seed):
    contract = _contract(db)
    line = _line(db, contract, qty=30)
    db.add_all([
        License(product_id=seed["product"].id, seats=10, contract_line_id=line.id),
        License(product_id=seed["product"].id, seats=5, contract_line_id=line.id),
    ])
    dead = License(product_id=seed["product"].id, seats=7, contract_line_id=line.id)
    _soft_delete(dead)
    db.add(dead)
    db.flush()
    assert line_received_qty(db, line) == 15
    db.refresh(line)
    assert line.qty_delivered == 15
    assert line.qty_remaining == 15


def test_hardware_line_received_still_counts_assets(db, seed):
    contract = _contract(db)
    line = _line(db, contract, kind=ContractItemKind.HARDWARE, qty=2, item_type="Laptop")
    db.add(Asset(asset_code="SW-HW-1", category_id=seed["cat"].id, contract_line_id=line.id))
    # Gói license gắn nhầm vào hạng mục phần cứng không được tính là thiết bị đã nhận
    db.flush()
    assert line_received_qty(db, line) == 1


def test_software_only_contract_becomes_delivered(db, seed):
    contract = _contract(db)
    line = _line(db, contract, qty=30)
    assert sync_contract_delivery_status(db, contract.id) == DeliveryStatus.PENDING
    db.add(License(product_id=seed["product"].id, seats=30, contract_line_id=line.id))
    db.flush()
    assert sync_contract_delivery_status(db, contract.id) == DeliveryStatus.DELIVERED


def test_mixed_contract_needs_both_kinds_delivered(db, seed):
    contract = _contract(db)
    sw = _line(db, contract, qty=5)
    hw = _line(db, contract, kind=ContractItemKind.HARDWARE, qty=1, item_type="Laptop")
    db.add(License(product_id=seed["product"].id, seats=5, contract_line_id=sw.id))
    db.flush()
    assert sync_contract_delivery_status(db, contract.id) == DeliveryStatus.PENDING
    db.add(Asset(asset_code="SW-MIX-1", category_id=seed["cat"].id, contract_line_id=hw.id))
    db.flush()
    assert sync_contract_delivery_status(db, contract.id) == DeliveryStatus.DELIVERED


# ---------------------------------------------------------------------------
# Service nhận phần mềm
# ---------------------------------------------------------------------------


def test_receive_creates_license_linked_to_line_and_contract(db, seed):
    contract = _contract(db)
    line = _line(db, contract, qty=30)
    lic = receive_license_for_line(
        db, line.id, product_id=seed["product"].id, seats=10,
        start_date=TODAY, expiry_date=TODAY + dt.timedelta(days=365),
        note="Đợt 1", user_id=seed["user"].id,
    )
    assert lic.contract_line_id == line.id
    assert lic.contract_id == contract.id
    assert lic.seats == 10
    assert contract.delivery_status == DeliveryStatus.PENDING
    audit = db.scalar(
        select(AuditLog).where(
            AuditLog.table_name == "licenses",
            AuditLog.record_id == lic.id,
            AuditLog.action == AuditAction.CREATE,
        )
    )
    assert audit is not None


def test_receive_final_batch_marks_contract_delivered(db, seed):
    contract = _contract(db)
    line = _line(db, contract, qty=30)
    receive_license_for_line(db, line.id, product_id=seed["product"].id, seats=10)
    receive_license_for_line(db, line.id, product_id=seed["product"].id, seats=20)
    assert contract.delivery_status == DeliveryStatus.DELIVERED


def test_receive_cannot_exceed_ordered_seats(db, seed):
    contract = _contract(db)
    line = _line(db, contract, qty=30)
    receive_license_for_line(db, line.id, product_id=seed["product"].id, seats=25)
    with pytest.raises(ValueError):
        receive_license_for_line(db, line.id, product_id=seed["product"].id, seats=6)
    assert line_received_qty(db, line) == 25


def test_receive_rejects_hardware_line(db, seed):
    contract = _contract(db)
    line = _line(db, contract, kind=ContractItemKind.HARDWARE, qty=5, item_type="Laptop")
    with pytest.raises(ValueError):
        receive_license_for_line(db, line.id, product_id=seed["product"].id, seats=1)


@pytest.mark.parametrize("seats", [0, -3])
def test_receive_rejects_non_positive_seats(db, seed, seats):
    contract = _contract(db)
    line = _line(db, contract, qty=30)
    with pytest.raises(ValueError):
        receive_license_for_line(db, line.id, product_id=seed["product"].id, seats=seats)


def test_receive_rejects_deleted_line_contract_or_product(db, seed):
    contract = _contract(db)
    line = _line(db, contract, qty=30)
    _soft_delete(seed["product"])
    db.flush()
    with pytest.raises(ValueError):
        receive_license_for_line(db, line.id, product_id=seed["product"].id, seats=1)

    seed["product"].is_deleted = False
    seed["product"].deleted_at = None
    seed["product"].delete_reason = None
    _soft_delete(contract)
    db.flush()
    with pytest.raises(ValueError):
        receive_license_for_line(db, line.id, product_id=seed["product"].id, seats=1)


def test_receive_rejects_expiry_before_start(db, seed):
    contract = _contract(db)
    line = _line(db, contract, qty=30)
    with pytest.raises(ValueError):
        receive_license_for_line(
            db, line.id, product_id=seed["product"].id, seats=1,
            start_date=TODAY, expiry_date=TODAY - dt.timedelta(days=1),
        )


# ---------------------------------------------------------------------------
# Quy tắc trên form SQLAdmin
# ---------------------------------------------------------------------------


def test_asset_cannot_be_attached_to_a_software_line(db, seed):
    contract = _contract(db)
    line = _line(db, contract, qty=30)
    data = {"asset_code": "SW-A1", "status": "IN_STOCK", "contract_line": str(line.id)}
    with pytest.raises(ValueError):
        _run(AssetAdmin().on_model_change(data, Asset(), True, _req(db)))


def test_license_form_rejects_hardware_line(db, seed):
    contract = _contract(db)
    line = _line(db, contract, kind=ContractItemKind.HARDWARE, qty=5, item_type="Laptop")
    data = {"product": str(seed["product"].id), "seats": 2, "contract_line": str(line.id)}
    with pytest.raises(ValueError):
        _run(LicenseAdmin().on_model_change(data, License(), True, _req(db)))


def test_license_form_links_line_and_fills_contract(db, seed):
    contract = _contract(db)
    line = _line(db, contract, qty=30)
    data = {"product": str(seed["product"].id), "seats": 10, "contract_line": str(line.id)}
    _run(LicenseAdmin().on_model_change(data, License(), True, _req(db)))
    assert data["contract_id"] == contract.id


def test_license_form_cannot_exceed_line_quantity(db, seed):
    contract = _contract(db)
    line = _line(db, contract, qty=30)
    existing = License(product_id=seed["product"].id, seats=25, contract_line_id=line.id, contract_id=contract.id)
    db.add(existing)
    db.flush()
    # Gói mới làm vượt
    data = {"product": str(seed["product"].id), "seats": 6, "contract_line": str(line.id)}
    with pytest.raises(ValueError):
        _run(LicenseAdmin().on_model_change(data, License(), True, _req(db)))
    # Tăng seat của chính gói đang có: 25 -> 31 vượt, 25 -> 30 hợp lệ (không tự đếm chính nó)
    with pytest.raises(ValueError):
        _run(LicenseAdmin().on_model_change({"seats": 31, "contract_line": str(line.id)}, existing, False, _req(db)))
    _run(LicenseAdmin().on_model_change({"seats": 30, "contract_line": str(line.id)}, existing, False, _req(db)))


def test_license_form_resyncs_contract_after_seat_change(db, seed):
    contract = _contract(db)
    line = _line(db, contract, qty=30)
    lic = License(product_id=seed["product"].id, seats=30, contract_line_id=line.id, contract_id=contract.id)
    db.add(lic)
    db.flush()
    sync_contract_delivery_status(db, contract.id)
    assert contract.delivery_status == DeliveryStatus.DELIVERED

    view = LicenseAdmin()
    req = _req(db, user_id=seed["user"].id)
    data = {"seats": 20, "contract_line": str(line.id)}
    _run(view.on_model_change(data, lic, False, req))
    lic.seats = 20
    db.flush()
    _run(view.after_model_change(data, lic, False, req))
    assert contract.delivery_status == DeliveryStatus.PENDING


def test_line_kind_cannot_change_after_receiving(db, seed):
    contract = _contract(db)
    line = _line(db, contract, qty=30)
    db.add(License(product_id=seed["product"].id, seats=5, contract_line_id=line.id))
    db.flush()
    with pytest.raises(ValueError):
        _run(ContractLineAdmin().on_model_change({"item_kind": "HARDWARE", "qty_ordered": 30}, line, False, _req(db)))
    # Hạng mục chưa nhận gì thì đổi loại được
    empty = _line(db, contract, qty=3, item_type="Visio")
    _run(ContractLineAdmin().on_model_change({"item_kind": "HARDWARE", "qty_ordered": 3}, empty, False, _req(db)))


def test_software_line_qty_cannot_drop_below_received_seats(db, seed):
    contract = _contract(db)
    line = _line(db, contract, qty=30)
    db.add(License(product_id=seed["product"].id, seats=20, contract_line_id=line.id))
    db.flush()
    with pytest.raises(ValueError):
        _run(ContractLineAdmin().on_model_change({"item_kind": "SOFTWARE", "qty_ordered": 19}, line, False, _req(db)))


def test_software_line_with_licenses_cannot_be_deleted(db, seed):
    contract = _contract(db)
    line = _line(db, contract, qty=30)
    db.add(License(product_id=seed["product"].id, seats=20, contract_line_id=line.id))
    db.flush()
    req = DummyRequest(session={"user_id": seed["user"].id}, db=db, query_params={"delete_reason": "x"})
    with pytest.raises(HTTPException) as exc:
        _run(ContractLineAdmin().delete_model(req, line.id))
    assert exc.value.status_code == 400
    assert line.is_deleted is False


def test_deleting_a_license_reopens_the_contract(db, seed):
    contract = _contract(db)
    line = _line(db, contract, qty=30)
    lic = receive_license_for_line(db, line.id, product_id=seed["product"].id, seats=30)
    assert contract.delivery_status == DeliveryStatus.DELIVERED
    req = DummyRequest(session={"user_id": seed["user"].id}, db=db, query_params={"delete_reason": "nhập sai"})
    _run(LicenseAdmin().delete_model(req, lic.id))
    assert lic.is_deleted is True
    assert contract.delivery_status == DeliveryStatus.PENDING


# ---------------------------------------------------------------------------
# Màn hình nhận phần mềm (HTTP)
# ---------------------------------------------------------------------------


def test_receive_software_page_renders(admin_client, db, seed):
    contract = _contract(db)
    line = _line(db, contract, qty=30)
    res = admin_client.get(f"/admin/contract-line/{line.id}/receive-software")
    assert res.status_code == 200
    assert seed["product"].name in res.text
    assert "Office LTSC 2024" in res.text


def test_receive_software_post_creates_license(admin_client, db, seed):
    contract = _contract(db)
    line = _line(db, contract, qty=30)
    res = admin_client.post(
        f"/admin/contract-line/{line.id}/receive-software",
        json={
            "product_id": seed["product"].id,
            "seats": 30,
            "start_date": TODAY.isoformat(),
            "expiry_date": (TODAY + dt.timedelta(days=365)).isoformat(),
            "note": "Giao đủ",
        },
    )
    assert res.status_code == 200, res.text
    assert res.json()["success"] is True
    lic = db.scalar(select(License).where(License.contract_line_id == line.id))
    assert lic is not None and lic.seats == 30
    assert lic.created_by == seed["user"].id
    db.refresh(contract)
    assert contract.delivery_status == DeliveryStatus.DELIVERED


def test_receive_software_post_over_quantity_is_400(admin_client, db, seed):
    contract = _contract(db)
    line = _line(db, contract, qty=30)
    res = admin_client.post(
        f"/admin/contract-line/{line.id}/receive-software",
        json={"product_id": seed["product"].id, "seats": 31},
    )
    assert res.status_code == 400
    assert db.scalar(select(License).where(License.contract_line_id == line.id)) is None


@pytest.mark.parametrize("payload", [
    {"seats": 5},
    {"product_id": "abc", "seats": 5},
    {"product_id": "REAL", "seats": "nhiều"},
    {"product_id": "REAL", "seats": True},
    {"product_id": "REAL", "seats": 5, "expiry_date": "31/12/2026"},
])
def test_receive_software_post_bad_input_is_400(admin_client, db, seed, payload):
    contract = _contract(db)
    line = _line(db, contract, qty=30)
    if payload.get("product_id") == "REAL":
        payload = {**payload, "product_id": seed["product"].id}
    res = admin_client.post(f"/admin/contract-line/{line.id}/receive-software", json=payload)
    assert res.status_code == 400
    assert db.scalar(select(License).where(License.contract_line_id == line.id)) is None


def test_receive_software_requires_license_add_permission(client, db, seed):
    role = Role(code=RoleCode.EXECUTIVE.value, name_en="Executive")
    db.add(role)
    db.flush()
    _grant(db, role, {Module.LICENSES: [PermissionAction.VIEW], Module.CONTRACTS: [PermissionAction.VIEW]})
    viewer = User(username="sw_viewer", password_hash=hash_password("Passw0rd!xyz"), display_name="V", role_id=role.id)
    db.add(viewer)
    db.flush()
    contract = _contract(db)
    line = _line(db, contract, qty=30)
    _login(client, viewer, RoleCode.EXECUTIVE.value)
    assert client.get(f"/admin/contract-line/{line.id}/receive-software").status_code == 403
    res = client.post(
        f"/admin/contract-line/{line.id}/receive-software",
        json={"product_id": seed["product"].id, "seats": 1},
    )
    assert res.status_code == 403
    assert db.scalar(select(License).where(License.contract_line_id == line.id)) is None


def test_hardware_receive_screen_redirects_software_lines(admin_client, db, seed):
    contract = _contract(db)
    line = _line(db, contract, qty=30)
    res = admin_client.get(f"/admin/contract-line/{line.id}/receive", follow_redirects=False)
    assert res.status_code in (302, 303, 307)
    assert res.headers["location"].endswith(f"/admin/contract-line/{line.id}/receive-software")


def test_hardware_batch_receive_refuses_software_lines(admin_client, db, seed):
    contract = _contract(db)
    line = _line(db, contract, qty=30)
    res = admin_client.post(
        f"/admin/contract-line/{line.id}/receive",
        json={"category_id": seed["cat"].id, "items": [{"serial": "SW-SN-1"}]},
    )
    assert res.status_code == 400
    assert db.scalar(select(Asset).where(Asset.serial == "SW-SN-1")) is None


def test_software_receive_screen_refuses_hardware_lines(admin_client, db, seed):
    contract = _contract(db)
    line = _line(db, contract, kind=ContractItemKind.HARDWARE, qty=2, item_type="Laptop")
    res = admin_client.post(
        f"/admin/contract-line/{line.id}/receive-software",
        json={"product_id": seed["product"].id, "seats": 1},
    )
    assert res.status_code == 400


def test_restoring_a_license_over_line_quantity_is_refused(admin_client, db, seed):
    contract = _contract(db)
    line = _line(db, contract, qty=30)
    old = receive_license_for_line(db, line.id, product_id=seed["product"].id, seats=20)
    _soft_delete(old)
    db.flush()
    receive_license_for_line(db, line.id, product_id=seed["product"].id, seats=30)
    res = admin_client.post("/admin/trash/restore", data={"entity_type": "license", "item_id": old.id})
    assert res.status_code == 400
    assert old.is_deleted is True


def test_restoring_a_license_resyncs_the_contract(admin_client, db, seed):
    contract = _contract(db)
    line = _line(db, contract, qty=30)
    lic = receive_license_for_line(db, line.id, product_id=seed["product"].id, seats=30)
    _soft_delete(lic)
    db.flush()
    sync_contract_delivery_status(db, contract.id)
    assert contract.delivery_status == DeliveryStatus.PENDING
    res = admin_client.post("/admin/trash/restore", data={"entity_type": "license", "item_id": lic.id})
    assert res.status_code == 200, res.text
    assert contract.delivery_status == DeliveryStatus.DELIVERED


def test_contract_line_form_creates_a_software_line(admin_client, db, seed):
    contract = _contract(db)
    res = admin_client.post("/admin/contract-line/create", data={
        "contract": str(contract.id),
        "item_type": "Visio Standard",
        "item_kind": "SOFTWARE",
        "qty_ordered": "4",
    }, follow_redirects=True)
    assert res.status_code == 200
    line = db.scalar(select(ContractLine).where(ContractLine.item_type == "Visio Standard"))
    assert line is not None
    assert line.item_kind == ContractItemKind.SOFTWARE


def test_contract_line_list_points_software_lines_to_software_receive(admin_client, db, seed):
    contract = _contract(db)
    line = _line(db, contract, qty=30)
    admin_client.get("/admin/set-lang?lang=vi&next=/admin", follow_redirects=False)
    html = admin_client.get("/admin/contract-line/list").text
    assert f"/admin/contract-line/{line.id}/receive-software" in html
    assert "Phần mềm</span>" in html
    assert "Nhận phần mềm" in html


def test_software_receive_screen_redirects_hardware_lines(admin_client, db, seed):
    contract = _contract(db)
    line = _line(db, contract, kind=ContractItemKind.HARDWARE, qty=2, item_type="Laptop")
    res = admin_client.get(f"/admin/contract-line/{line.id}/receive-software", follow_redirects=False)
    assert res.status_code == 303
    assert res.headers["location"].endswith(f"/admin/contract-line/{line.id}/receive")


# ---------------------------------------------------------------------------
# Nhận nhiều đợt: gộp vào một gói thay vì sinh thêm dòng trong Kho License
# ---------------------------------------------------------------------------


def _packages(db, line):
    return db.scalars(
        select(License).where(License.contract_line_id == line.id, License.is_deleted.is_(False))
    ).all()


def test_second_batch_of_same_product_is_merged_into_one_package(db, seed):
    contract = _contract(db)
    line = _line(db, contract, qty=30)
    first = receive_license_for_line(db, line.id, product_id=seed["product"].id, seats=10, user_id=seed["user"].id)
    second = receive_license_for_line(db, line.id, product_id=seed["product"].id, seats=20, user_id=seed["user"].id)
    assert second.id == first.id
    packages = _packages(db, line)
    assert len(packages) == 1
    assert packages[0].seats == 30
    assert contract.delivery_status == DeliveryStatus.DELIVERED


def test_merged_batch_is_recorded_in_audit_log(db, seed):
    contract = _contract(db)
    line = _line(db, contract, qty=30)
    lic = receive_license_for_line(db, line.id, product_id=seed["product"].id, seats=10, user_id=seed["user"].id)
    receive_license_for_line(db, line.id, product_id=seed["product"].id, seats=20, user_id=seed["user"].id)
    update = db.scalar(
        select(AuditLog).where(
            AuditLog.table_name == "licenses",
            AuditLog.record_id == lic.id,
            AuditLog.action == AuditAction.UPDATE,
        )
    )
    assert update is not None
    assert update.before_after["before"]["seats"] == 10
    assert update.before_after["after"]["seats"] == 30
    assert update.before_after["extra"]["received_seats"] == 20


def test_batch_with_different_expiry_stays_a_separate_package(db, seed):
    contract = _contract(db)
    line = _line(db, contract, qty=30)
    receive_license_for_line(
        db, line.id, product_id=seed["product"].id, seats=10, expiry_date=TODAY + dt.timedelta(days=365)
    )
    receive_license_for_line(
        db, line.id, product_id=seed["product"].id, seats=20, expiry_date=TODAY + dt.timedelta(days=730)
    )
    assert sorted(p.seats for p in _packages(db, line)) == [10, 20]


def test_batch_of_another_product_stays_a_separate_package(db, seed):
    from app.models import LicenseProduct

    other = LicenseProduct(name="Visio")
    db.add(other)
    db.flush()
    contract = _contract(db)
    line = _line(db, contract, qty=30)
    receive_license_for_line(db, line.id, product_id=seed["product"].id, seats=10)
    receive_license_for_line(db, line.id, product_id=other.id, seats=5)
    assert len(_packages(db, line)) == 2


def test_batch_is_not_merged_into_a_deleted_package(db, seed):
    contract = _contract(db)
    line = _line(db, contract, qty=30)
    old = receive_license_for_line(db, line.id, product_id=seed["product"].id, seats=10)
    _soft_delete(old)
    db.flush()
    new = receive_license_for_line(db, line.id, product_id=seed["product"].id, seats=10)
    assert new.id != old.id
    assert old.seats == 10 and old.is_deleted is True


def test_merged_batch_still_cannot_exceed_ordered_quantity(db, seed):
    contract = _contract(db)
    line = _line(db, contract, qty=30)
    lic = receive_license_for_line(db, line.id, product_id=seed["product"].id, seats=25)
    with pytest.raises(ValueError):
        receive_license_for_line(db, line.id, product_id=seed["product"].id, seats=6)
    assert lic.seats == 25
