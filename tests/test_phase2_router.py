"""Kiểm thử Router API Bàn giao & Thu hồi Tài sản - Giai đoạn 2."""

from __future__ import annotations

import datetime as dt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import create_session_token
from app.db import get_db
from app.enums import DEFAULT_ROLE_PERMISSIONS, RoleCode
from app.main import app
from app.models import RolePermission


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def override_db(db: Session, monkeypatch):
    """Đảm bảo TestClient dùng chung session với transaction trong test."""
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


@pytest.fixture
def auth_client(client: TestClient, db: Session, seed) -> TestClient:
    user = seed["user"]
    role = seed["role"]

    # Đảm bảo role có đủ quyền mặc định của ADMIN
    for mod, actions in DEFAULT_ROLE_PERMISSIONS[RoleCode.ADMIN].items():
        for act in actions:
            existing = db.scalar(
                select(RolePermission).where(
                    RolePermission.role_id == role.id,
                    RolePermission.module == mod.value,
                    RolePermission.action == act.value,
                )
            )
            if not existing:
                db.add(RolePermission(role_id=role.id, module=mod.value, action=act.value))
    db.flush()

    token = create_session_token(
        {"user_id": user.id, "username": user.username, "role": role.code}
    )
    client.cookies.set("itam_session", token)
    return client


def test_api_search_persons(auth_client: TestClient, db: Session, seed):
    res = auth_client.get("/admin/api/persons/search?q=Nguyen")
    assert res.status_code == 200
    data = res.json()
    assert len(data) >= 1
    assert data[0]["staff_code"] == seed["person"].staff_code


def test_api_assign_asset_endpoint(auth_client: TestClient, db: Session, seed):
    asset = seed["asset"]
    person = seed["person"]

    today_str = dt.date.today().isoformat()
    payload = {
        "person_id": person.id,
        "borrowed_at": today_str,
        "note": "Giao máy mới",
    }
    res = auth_client.post(f"/admin/assets/{asset.id}/assign", json=payload)
    assert res.status_code == 200
    res_data = res.json()
    assert res_data["success"] is True
    assert res_data["asset_status"] == "IN_USE"


def test_api_return_asset_endpoint(auth_client: TestClient, db: Session, seed):
    asset = seed["asset"]
    person = seed["person"]
    today = dt.date.today()

    # 1. Bàn giao trước
    auth_client.post(
        f"/admin/assets/{asset.id}/assign",
        json={"person_id": person.id, "borrowed_at": today.isoformat()},
    )

    # 2. Thu hồi
    payload = {
        "returned_at": today.isoformat(),
        "return_status": "IN_STOCK",
        "note": "Nhân viên trả máy nguyên vẹn",
    }
    res = auth_client.post(f"/admin/assets/{asset.id}/return", json=payload)
    assert res.status_code == 200
    res_data = res.json()
    assert res_data["success"] is True
    assert res_data["asset_status"] == "IN_STOCK"


def test_api_asset_history_endpoint(auth_client: TestClient, db: Session, seed):
    asset = seed["asset"]
    person = seed["person"]
    today = dt.date.today()

    auth_client.post(
        f"/admin/assets/{asset.id}/assign",
        json={"person_id": person.id, "borrowed_at": today.isoformat(), "note": "Ghi chú test"},
    )

    res = auth_client.get(f"/admin/assets/{asset.id}/history")
    assert res.status_code == 200
    history = res.json()
    assert len(history) >= 1
    assert history[0]["staff_code"] == person.staff_code
