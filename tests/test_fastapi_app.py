import pytest
from datetime import date
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.database import Base, engine, SessionLocal
from app.services.seed import seed_all_data
from app.models import Asset, AssetCategory, Person, Department, AccessCard

@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed_all_data(db)
    finally:
        db.close()

@pytest.mark.anyio
async def test_unauthenticated_redirects_to_login():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/login"

@pytest.mark.anyio
async def test_swagger_docs_accessible():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/docs")
        assert response.status_code == 200

@pytest.mark.anyio
async def test_api_login_success():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/v1/auth/login", json={
            "username": "admin",
            "password": "tokuadmin2026"
        })
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["username"] == "admin"
        assert data["role"] == "it_admin"

@pytest.mark.anyio
async def test_api_login_failure():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/v1/auth/login", json={
            "username": "admin",
            "password": "wrong_password"
        })
        assert response.status_code == 401

@pytest.mark.anyio
async def test_api_dashboard_stats():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/stats/dashboard")
        assert response.status_code == 200
        data = response.json()
        assert "asset_stats" in data
        assert "total" in data["asset_stats"]
        assert "expiring_licenses" in data
        assert "active_card_loans" in data

@pytest.mark.anyio
async def test_web_login_flow_and_dashboard():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        login_res = await client.post("/login", data={
            "username": "admin",
            "password": "tokuadmin2026"
        }, follow_redirects=True)
        assert login_res.status_code == 200
        assert "Total IT Assets" in login_res.text or "Tokuyama ITAM" in login_res.text

@pytest.mark.anyio
async def test_web_search_and_trash():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Login first to obtain session cookie
        await client.post("/login", data={
            "username": "admin",
            "password": "tokuadmin2026"
        })
        
        # Test search
        search_res = await client.get("/search?q=TVN")
        assert search_res.status_code == 200
        assert "Search" in search_res.text or "Tìm kiếm" in search_res.text

        # Test trash view
        trash_res = await client.get("/trash")
        assert trash_res.status_code == 200
        assert "Thùng Rác" in trash_res.text or "Trash" in trash_res.text

@pytest.mark.anyio
async def test_api_asset_crud():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Create an asset
        create_res = await client.post("/api/v1/assets", json={
            "asset_code": "LAP-2026-TEST",
            "model": "ThinkPad T14 Gen 4",
            "serial": "SN-TEST-9999",
            "status": "in_stock",
            "mac_address": "AA:BB:CC:DD:EE:01",
            "ip_address": "192.168.1.101"
        })
        assert create_res.status_code == 200
        asset_data = create_res.json()
        assert asset_data["asset_code"] == "LAP-2026-TEST"
        asset_id = asset_data["id"]

        # List assets
        list_res = await client.get("/api/v1/assets")
        assert list_res.status_code == 200
        assets = list_res.json()
        assert any(a["id"] == asset_id for a in assets)

        # Global search via API
        search_api = await client.get("/api/v1/search?q=TEST-9999")
        assert search_api.status_code == 200
        search_data = search_api.json()
        assert len(search_data["assets"]) >= 1
        assert search_data["assets"][0]["serial"] == "SN-TEST-9999"

@pytest.mark.anyio
async def test_soft_delete_and_restore():
    db = SessionLocal()
    try:
        # Create asset directly
        asset = Asset(
            asset_code="DEL-TEST-001",
            model="Latitude 5540",
            serial="SN-DEL-001",
            status="in_stock"
        )
        db.add(asset)
        db.commit()
        db.refresh(asset)
        asset_id = asset.id

        # Perform soft delete
        asset.soft_delete(user_id=1, reason="Unit test decommission")
        db.commit()

        # Query normal assets
        active_assets = db.query(Asset).filter(Asset.is_deleted == False).all()
        assert not any(a.id == asset_id for a in active_assets)

        # Query deleted
        deleted_asset = db.query(Asset).filter(Asset.id == asset_id, Asset.is_deleted == True).first()
        assert deleted_asset is not None
        assert deleted_asset.delete_reason == "Unit test decommission"

        # Restore
        deleted_asset.restore()
        db.commit()
        restored = db.query(Asset).filter(Asset.id == asset_id, Asset.is_deleted == False).first()
        assert restored is not None
        assert restored.is_deleted is False
    finally:
        db.close()
