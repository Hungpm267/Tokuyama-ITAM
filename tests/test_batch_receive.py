"""Kiểm thử tính năng Nhập kho thiết bị theo lô từ Hạng mục Hợp đồng."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import create_session_token, hash_password
from app.db import get_db
from app.enums import AssetStatus, AuditAction, DeliveryStatus, RoleCode
from app.main import app
from app.models import (
    Asset,
    AssetCategory,
    AuditLog,
    Contract,
    ContractLine,
    Role,
    User,
)


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def override_db(db: Session, monkeypatch):
    """Đảm bảo TestClient dùng chung transaction với fixture db trong test."""
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

    yield
    app.dependency_overrides.clear()


def _ensure_role(db: Session, code: str, name_en: str) -> Role:
    from app.enums import DEFAULT_ROLE_PERMISSIONS
    from app.models import RolePermission

    role = db.scalar(select(Role).where(Role.code == code))
    if not role:
        role = Role(code=code, name_en=name_en)
        db.add(role)
        db.flush()
        role_enum = None
        for r in RoleCode:
            if r.value == code:
                role_enum = r
                break
        if role_enum and role_enum in DEFAULT_ROLE_PERMISSIONS:
            for mod, actions in DEFAULT_ROLE_PERMISSIONS[role_enum].items():
                for act in actions:
                    db.add(RolePermission(role_id=role.id, module=mod, action=act))
            db.flush()
    return role


def _create_user(db: Session, username: str, role_code: str) -> User:
    role = _ensure_role(db, role_code, role_code)
    user = db.scalar(select(User).where(User.username == username))
    if not user:
        user = User(
            username=username,
            password_hash=hash_password("Pass123456!"),
            display_name=username,
            role_id=role.id,
            preferred_lang="vi",
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


@pytest.fixture
def admin_user(db: Session) -> User:
    return _create_user(db, "batch_admin", RoleCode.ADMIN.value)


@pytest.fixture
def viewer_user(db: Session) -> User:
    return _create_user(db, "batch_viewer", RoleCode.EXECUTIVE.value)


@pytest.fixture
def admin_client(client: TestClient, admin_user: User) -> TestClient:
    token = create_session_token(
        {"user_id": admin_user.id, "username": admin_user.username, "role": admin_user.role.code}
    )
    client.cookies.set("itam_session", token)
    return client


@pytest.fixture
def viewer_client(client: TestClient, viewer_user: User) -> TestClient:
    token = create_session_token(
        {"user_id": viewer_user.id, "username": viewer_user.username, "role": viewer_user.role.code}
    )
    client.cookies.set("itam_session", token)
    return client


@pytest.fixture
def sample_contract_setup(db: Session):
    cat = AssetCategory(name_en="Laptop", name_ja="ノートパソコン")
    db.add(cat)
    db.flush()

    contract = Contract(
        code="KDDI-BATCH-2026",
        vendor_name="KDDI Vietnam",
        delivery_status=DeliveryStatus.PENDING,
    )
    db.add(contract)
    db.flush()

    line = ContractLine(
        contract_id=contract.id,
        item_type="Laptop Dell Latitude 5440",
        spec="Core i5-1335U / 16GB RAM / 512GB SSD",
        qty_ordered=3,
    )
    db.add(line)
    db.commit()
    db.refresh(cat)
    db.refresh(contract)
    db.refresh(line)

    return {"category": cat, "contract": contract, "line": line}


def test_batch_receive_unauthorized(client: TestClient, sample_contract_setup):
    line_id = sample_contract_setup["line"].id
    resp = client.get(f"/admin/contract-line/{line_id}/receive")
    assert resp.status_code == 401


def test_batch_receive_forbidden(viewer_client: TestClient, sample_contract_setup):
    line_id = sample_contract_setup["line"].id
    resp = viewer_client.get(f"/admin/contract-line/{line_id}/receive")
    assert resp.status_code == 403


def test_batch_receive_not_found(admin_client: TestClient):
    resp = admin_client.get("/admin/contract-line/999999/receive")
    assert resp.status_code == 404


def test_batch_receive_page_get(admin_client: TestClient, sample_contract_setup):
    line = sample_contract_setup["line"]
    resp = admin_client.get(f"/admin/contract-line/{line.id}/receive")
    assert resp.status_code == 200
    assert "KDDI-BATCH-2026" in resp.text
    assert "Laptop Dell Latitude 5440" in resp.text
    assert "Nhập kho thiết bị theo lô" in resp.text


def test_batch_receive_post_success(admin_client: TestClient, sample_contract_setup, db: Session):
    line = sample_contract_setup["line"]
    cat = sample_contract_setup["category"]
    contract = sample_contract_setup["contract"]

    payload = {
        "category_id": cat.id,
        "model": "Dell Latitude 5440",
        "form_factor": "Laptop",
        "note": "Đợt giao hàng 1",
        "items": [
            {
                "serial": "SN-DELL-001",
                "asset_code": "TVC-EM0081",
                "vendor_code": "TKY-PC0031",
                "mac_ethernet": "00:11:22:33:44:01",
                "mac_wifi": "00:11:22:33:44:02",
            },
            {
                "serial": "SN-DELL-002",
                "asset_code": "TVC-EM0082",
                "vendor_code": "TKY-PC0032",
                "mac_ethernet": "00:11:22:33:44:03",
                "mac_wifi": "00:11:22:33:44:04",
            },
            {
                "serial": "SN-DELL-003",
                "asset_code": "TVC-EM0083",
                "vendor_code": "TKY-PC0033",
                "mac_ethernet": "00:11:22:33:44:05",
                "mac_wifi": "00:11:22:33:44:06",
            },
        ],
    }

    resp = admin_client.post(
        f"/admin/contract-line/{line.id}/receive",
        json=payload,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["count"] == 3

    # Kiểm tra các Asset đã được lưu trong CSDL
    assets = db.scalars(
        select(Asset).where(Asset.contract_line_id == line.id, Asset.is_deleted.is_(False))
    ).all()
    assert len(assets) == 3
    serials = {a.serial for a in assets}
    assert serials == {"SN-DELL-001", "SN-DELL-002", "SN-DELL-003"}
    for a in assets:
        assert a.category_id == cat.id
        assert a.status == AssetStatus.IN_STOCK
        assert a.model == "Dell Latitude 5440"

    # Kiểm tra tiến độ contract line
    db.refresh(line)
    assert line.qty_delivered == 3
    assert line.qty_remaining == 0

    # Kiểm tra tự động cập nhật trạng thái hợp đồng thành DELIVERED
    db.refresh(contract)
    assert contract.delivery_status == DeliveryStatus.DELIVERED

    # Kiểm tra AuditLog được ghi lại cho từng máy
    logs = db.scalars(
        select(AuditLog).where(
            AuditLog.table_name == "assets",
            AuditLog.action == AuditAction.CREATE,
            AuditLog.record_id.in_([a.id for a in assets]),
        )
    ).all()
    assert len(logs) == 3


def test_batch_receive_internal_duplicates(admin_client: TestClient, sample_contract_setup):
    line = sample_contract_setup["line"]
    cat = sample_contract_setup["category"]

    # 1. Trùng Serial nội bộ
    payload_dup_serial = {
        "category_id": cat.id,
        "items": [
            {"serial": "SN-DUP-01", "asset_code": "TVC-EM0091"},
            {"serial": "SN-DUP-01", "asset_code": "TVC-EM0092"},
        ],
    }
    resp = admin_client.post(
        f"/admin/contract-line/{line.id}/receive",
        json=payload_dup_serial,
    )
    assert resp.status_code == 400
    assert "lặp lại" in resp.json()["detail"]

    # 2. Trùng GA code nội bộ
    payload_dup_ga = {
        "category_id": cat.id,
        "items": [
            {"serial": "SN-DUP-02", "asset_code": "TVC-EM0093"},
            {"serial": "SN-DUP-03", "asset_code": "TVC-EM0093"},
        ],
    }
    resp = admin_client.post(
        f"/admin/contract-line/{line.id}/receive",
        json=payload_dup_ga,
    )
    assert resp.status_code == 400
    assert "lặp lại" in resp.json()["detail"]


def test_batch_receive_db_duplicate(admin_client: TestClient, sample_contract_setup, db: Session):
    line = sample_contract_setup["line"]
    cat = sample_contract_setup["category"]

    # Tạo trước 1 asset đã tồn tại trong DB
    existing_asset = Asset(
        category_id=cat.id,
        serial="SN-ALREADY-EXISTS",
        asset_code="TVC-EM0099",
    )
    db.add(existing_asset)
    db.commit()

    # Thử gửi 1 lô có chứa serial trùng với DB
    payload = {
        "category_id": cat.id,
        "items": [
            {"serial": "SN-ALREADY-EXISTS", "asset_code": "TVC-EM0100"},
        ],
    }
    resp = admin_client.post(
        f"/admin/contract-line/{line.id}/receive",
        json=payload,
    )
    assert resp.status_code == 400
    assert "đã tồn tại trong hệ thống" in resp.json()["detail"]


def test_batch_receive_partial_delivery(admin_client: TestClient, db: Session):
    cat = AssetCategory(name_en="Server", name_ja="サーバー")
    db.add(cat)
    db.flush()

    contract = Contract(
        code="KDDI-PARTIAL-2026",
        delivery_status=DeliveryStatus.PENDING,
    )
    db.add(contract)
    db.flush()

    line1 = ContractLine(
        contract_id=contract.id,
        item_type="Server Rack",
        qty_ordered=5,
    )
    line2 = ContractLine(
        contract_id=contract.id,
        item_type="UPS 3000VA",
        qty_ordered=2,
    )
    db.add_all([line1, line2])
    db.commit()

    # Nhận 2 máy cho line1 (đặt 5, mới nhận 2)
    payload = {
        "category_id": cat.id,
        "items": [
            {"serial": "SRV-01", "asset_code": "TVC-SRV01"},
            {"serial": "SRV-02", "asset_code": "TVC-SRV02"},
        ],
    }
    resp = admin_client.post(
        f"/admin/contract-line/{line1.id}/receive",
        json=payload,
    )
    assert resp.status_code == 200

    db.refresh(line1)
    db.refresh(contract)
    assert line1.qty_delivered == 2
    assert line1.qty_remaining == 3
    # Hợp đồng chưa đủ nên vẫn là PENDING
    assert contract.delivery_status == DeliveryStatus.PENDING
