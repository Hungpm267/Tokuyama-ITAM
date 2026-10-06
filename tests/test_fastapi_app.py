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

@pytest.mark.anyio
async def test_admin_auth_only_permits_it_admin():
    from app.admin import authentication_backend
    from app.services.auth import create_session_token
    from starlette.requests import Request
    
    # Simulate a Request with non-it_admin token
    ga_token = create_session_token(user_id=99, role="ga_manager")
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/admin/",
        "headers": [(b"cookie", f"toku_session={ga_token}".encode("utf-8"))],
        "session": {}
    }
    request = Request(scope)
    is_authenticated = await authentication_backend.authenticate(request)
    assert is_authenticated is False, "Non-it_admin user should not be authenticated in /admin"

    # Simulate a Request with it_admin token
    admin_token = create_session_token(user_id=1, role="it_admin")
    scope_admin = {
        "type": "http",
        "method": "GET",
        "path": "/admin/",
        "headers": [(b"cookie", f"toku_session={admin_token}".encode("utf-8"))],
        "session": {}
    }
    request_admin = Request(scope_admin)
    is_admin_auth = await authentication_backend.authenticate(request_admin)
    assert is_admin_auth is True, "it_admin user must be authenticated in /admin"

def test_admin_categories_and_view_configurations():
    from app.admin import AssetAdmin, UserAdmin, LicenseAdmin, AccessCardAdmin, ContractAdmin
    
    # Check categorized groupings
    assert AssetAdmin.category is not None and len(AssetAdmin.category) > 0
    assert LicenseAdmin.category is not None and len(LicenseAdmin.category) > 0
    assert AccessCardAdmin.category is not None and len(AccessCardAdmin.category) > 0
    assert UserAdmin.category is not None and len(UserAdmin.category) > 0
    assert ContractAdmin.category is not None and len(ContractAdmin.category) > 0

    # Check export capability
    assert AssetAdmin.can_export is True
    
    # Check friendly column labels
    assert AssetAdmin.column_labels is not None
    assert "asset_code" in AssetAdmin.column_labels

@pytest.mark.anyio
async def test_admin_user_password_hashing():
    from app.admin import UserAdmin
    from app.models.user import User
    from starlette.requests import Request
    
    admin_view = UserAdmin()
    user = User(username="newuser", role="it_admin")
    data = {"password_hash": "plaintextpass123"}
    scope = {"type": "http", "session": {}}
    request = Request(scope)
    
    await admin_view.on_model_change(data, user, True, request)
    assert data["password_hash"].startswith("pbkdf2_sha256$")
    assert "plaintextpass123" not in data["password_hash"]

@pytest.mark.anyio
async def test_admin_soft_delete_and_audit_log():
    from app.admin import AssetAdmin
    from app.models.audit import AuditLog
    from starlette.requests import Request
    
    db = SessionLocal()
    try:
        # Create test asset
        asset = Asset(
            asset_code="ADMIN-DEL-01",
            model="Dell OptiPlex 7090",
            serial="SN-ADM-01",
            status="in_stock"
        )
        db.add(asset)
        db.commit()
        db.refresh(asset)
        asset_id = asset.id
    finally:
        db.close()

    admin_view = AssetAdmin()
    scope = {
        "type": "http",
        "session": {"user_id": 1, "user_name": "admin"}
    }
    request = Request(scope)
    await admin_view.delete_model(request, asset_id)

    db = SessionLocal()
    try:
        # Verify asset was soft-deleted, not removed
        deleted_asset = db.query(Asset).filter(Asset.id == asset_id).first()
        assert deleted_asset is not None
        assert deleted_asset.is_deleted is True

        # Verify audit log was created
        log = db.query(AuditLog).filter(
            AuditLog.table_name == "assets",
            AuditLog.record_id == asset_id,
            AuditLog.action == "delete"
        ).first()
        assert log is not None
        assert log.user_name == "admin"
    finally:
        db.close()

@pytest.mark.anyio
async def test_admin_http_dashboard_and_theme():
    from app.services.auth import create_session_token
    token = create_session_token(user_id=1, role="it_admin")
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Request /admin/ with session cookie
        client.cookies.set("toku_session", token)
        res = await client.get("/admin/", follow_redirects=True)
        assert res.status_code == 200
        # Check custom Tokuyama layout elements
        assert "toku-admin-sidebar" in res.text
        assert "Quay lại Dashboard" in res.text
        assert "Tokuyama" in res.text


