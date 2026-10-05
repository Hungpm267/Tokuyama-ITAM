from sqladmin import Admin, ModelView
from sqladmin.authentication import AuthenticationBackend
from starlette.requests import Request
from starlette.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database import engine, SessionLocal
from app.models import (
    User, Department, Person, AssetCategory, Asset, Assignment,
    LicenseProduct, License, LicenseAssignment, Room, AccessCard,
    AccessCardRoom, CardLoan, Contract, ContractLine, AuditLog
)
from app.services.auth import (
    authenticate_user, create_session_token, verify_session_token
)

class AdminAuth(AuthenticationBackend):
    async def login(self, request: Request) -> bool:
        form = await request.form()
        username = form.get("username")
        password = form.get("password")

        db = SessionLocal()
        try:
            user = authenticate_user(db, username, password)
            if user:
                token = create_session_token(user.id, user.role)
                request.session.update({"token": token, "role": user.role, "user_id": user.id})
                return True
        finally:
            db.close()
        return False

    async def logout(self, request: Request) -> bool:
        request.session.clear()
        return True

    async def authenticate(self, request: Request) -> bool:
        token = request.session.get("token")
        if not token:
            # Also check toku_session cookie
            token = request.cookies.get("toku_session")
        if not token:
            return False
        session_data = verify_session_token(token)
        return session_data is not None

authentication_backend = AdminAuth(secret_key="toku-admin-session-secret-key-2026")

# --- Model Views ---

class UserAdmin(ModelView, model=User):
    name = "User"
    name_plural = "Users & Roles"
    icon = "fa-solid fa-user-shield"
    column_list = [User.id, User.username, User.full_name, User.role, User.is_active, User.created_at]
    column_searchable_list = [User.username, User.full_name]

class DepartmentAdmin(ModelView, model=Department):
    name = "Department"
    name_plural = "Departments"
    icon = "fa-solid fa-building"
    column_list = [Department.id, Department.name_en, Department.name_ja, Department.is_deleted]
    column_searchable_list = [Department.name_en, Department.name_ja]

class PersonAdmin(ModelView, model=Person):
    name = "Personnel"
    name_plural = "Personnel Directory"
    icon = "fa-solid fa-users"
    column_list = [Person.id, Person.staff_code, Person.full_name, Person.department, Person.status, Person.is_deleted]
    column_searchable_list = [Person.staff_code, Person.full_name]

class AssetCategoryAdmin(ModelView, model=AssetCategory):
    name = "Asset Category"
    name_plural = "Asset Categories"
    icon = "fa-solid fa-tags"
    column_list = [AssetCategory.id, AssetCategory.name, AssetCategory.is_deleted]
    column_searchable_list = [AssetCategory.name]

class AssetAdmin(ModelView, model=Asset):
    name = "Asset"
    name_plural = "IT Hardware Assets"
    icon = "fa-solid fa-laptop"
    column_list = [
        Asset.id, Asset.asset_code, Asset.category, Asset.model,
        Asset.serial, Asset.mac_address, Asset.status, Asset.is_deleted
    ]
    column_searchable_list = [Asset.asset_code, Asset.serial, Asset.model, Asset.mac_address]
    column_sortable_list = [Asset.id, Asset.asset_code, Asset.status]

class AssignmentAdmin(ModelView, model=Assignment):
    name = "Hardware Loan"
    name_plural = "Hardware Loan History"
    icon = "fa-solid fa-handshake"
    column_list = [Assignment.id, Assignment.asset, Assignment.person, Assignment.borrowed_at, Assignment.returned_at]

class LicenseProductAdmin(ModelView, model=LicenseProduct):
    name = "Software Product"
    name_plural = "Software Catalog"
    icon = "fa-solid fa-cube"
    column_list = [LicenseProduct.id, LicenseProduct.name]
    column_searchable_list = [LicenseProduct.name]

class LicenseAdmin(ModelView, model=License):
    name = "License Package"
    name_plural = "Software Licenses"
    icon = "fa-solid fa-key"
    column_list = [License.id, License.product, License.seats, License.start_date, License.expiry_date]

class LicenseAssignmentAdmin(ModelView, model=LicenseAssignment):
    name = "License Assignment"
    name_plural = "License Allocations"
    icon = "fa-solid fa-id-card-clip"
    column_list = [LicenseAssignment.id, LicenseAssignment.license, LicenseAssignment.asset, LicenseAssignment.person, LicenseAssignment.assigned_at, LicenseAssignment.removed_at]

class RoomAdmin(ModelView, model=Room):
    name = "Room"
    name_plural = "Facility Rooms"
    icon = "fa-solid fa-door-open"
    column_list = [Room.id, Room.name]
    column_searchable_list = [Room.name]

class AccessCardAdmin(ModelView, model=AccessCard):
    name = "Access Card"
    name_plural = "Access Cards"
    icon = "fa-solid fa-address-card"
    column_list = [AccessCard.id, AccessCard.card_no, AccessCard.is_deleted]
    column_searchable_list = [AccessCard.card_no]

class AccessCardRoomAdmin(ModelView, model=AccessCardRoom):
    name = "Room Access Rule"
    name_plural = "Card-Room Access Rules"
    icon = "fa-solid fa-link"
    column_list = [AccessCardRoom.id, AccessCardRoom.card, AccessCardRoom.room]

class CardLoanAdmin(ModelView, model=CardLoan):
    name = "Card Check-out"
    name_plural = "Card Loan Registry"
    icon = "fa-solid fa-clock-rotate-left"
    column_list = [CardLoan.id, CardLoan.card, CardLoan.person, CardLoan.external_name, CardLoan.borrowed_at, CardLoan.returned_at]

class ContractAdmin(ModelView, model=Contract):
    name = "Contract"
    name_plural = "Contracts"
    icon = "fa-solid fa-file-contract"
    column_list = [Contract.id, Contract.code, Contract.delivery_status]
    column_searchable_list = [Contract.code]

class ContractLineAdmin(ModelView, model=ContractLine):
    name = "Contract Line"
    name_plural = "Contract Line Items"
    icon = "fa-solid fa-list-check"
    column_list = [ContractLine.id, ContractLine.contract, ContractLine.item_type, ContractLine.qty_ordered]

class AuditLogAdmin(ModelView, model=AuditLog):
    name = "Audit Log"
    name_plural = "Audit Trail (Immutable)"
    icon = "fa-solid fa-shield-halved"
    can_create = False
    can_edit = False
    can_delete = False
    column_list = [AuditLog.id, AuditLog.timestamp, AuditLog.user_name, AuditLog.action, AuditLog.table_name, AuditLog.record_id, AuditLog.changes_json]
    column_searchable_list = [AuditLog.table_name, AuditLog.user_name]

def setup_admin(app):
    admin = Admin(
        app,
        engine,
        title="Tokuyama ITAM Admin",
        authentication_backend=authentication_backend,
        base_url="/admin"
    )

    admin.add_view(UserAdmin)
    admin.add_view(DepartmentAdmin)
    admin.add_view(PersonAdmin)
    admin.add_view(AssetCategoryAdmin)
    admin.add_view(AssetAdmin)
    admin.add_view(AssignmentAdmin)
    admin.add_view(LicenseProductAdmin)
    admin.add_view(LicenseAdmin)
    admin.add_view(LicenseAssignmentAdmin)
    admin.add_view(RoomAdmin)
    admin.add_view(AccessCardAdmin)
    admin.add_view(AccessCardRoomAdmin)
    admin.add_view(CardLoanAdmin)
    admin.add_view(ContractAdmin)
    admin.add_view(ContractLineAdmin)
    admin.add_view(AuditLogAdmin)

    return admin
