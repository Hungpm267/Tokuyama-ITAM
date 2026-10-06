from datetime import datetime
import anyio
from typing import Any
from sqladmin import Admin, ModelView
from sqladmin.authentication import AuthenticationBackend
from starlette.requests import Request
from starlette.responses import RedirectResponse

from app.database import engine, SessionLocal
from app.models import (
    User, Department, Person, AssetCategory, Asset, Assignment,
    LicenseProduct, License, LicenseAssignment, Room, AccessCard,
    AccessCardRoom, CardLoan, Contract, ContractLine, AuditLog
)
from app.services.auth import (
    authenticate_user, create_session_token, verify_session_token, hash_password
)

COMMON_EXCLUDED_COLUMNS = [
    "created_at", "created_by_id", "updated_at", "updated_by_id",
    "is_deleted", "deleted_at", "deleted_by_id", "delete_reason"
]

class AdminAuth(AuthenticationBackend):
    async def login(self, request: Request) -> bool:
        form = await request.form()
        username = str(form.get("username", ""))
        password = str(form.get("password", ""))

        db = SessionLocal()
        try:
            user = authenticate_user(db, username, password)
            if user and user.role == "it_admin":
                token = create_session_token(user.id, user.role)
                request.session.update({
                    "token": token,
                    "role": user.role,
                    "user_id": user.id,
                    "user_name": user.username
                })
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
            token = request.cookies.get("toku_session")
        if not token:
            return False
            
        session_data = verify_session_token(token)
        if not session_data:
            return False
            
        user_id, role = session_data
        if role != "it_admin":
            return False
            
        if "user_id" not in request.session:
            request.session["user_id"] = user_id
            request.session["role"] = role
            
        return True

authentication_backend = AdminAuth(secret_key="toku-admin-session-secret-key-2026")

# --- Base Model View with Soft Delete, Audit Trail & Export ---

class BaseAdminView(ModelView):
    can_export = True
    page_size = 25
    page_size_options = [10, 25, 50, 100]
    form_excluded_columns = COMMON_EXCLUDED_COLUMNS

    async def after_model_change(self, data: dict, model: Any, is_created: bool, request: Request) -> None:
        action = "create" if is_created else "update"
        user_name = request.session.get("user_name") or "admin"
        user_id = request.session.get("user_id") or 1
        record_id = getattr(model, "id", None) or 0
        try:
            with SessionLocal() as db:
                log = AuditLog(
                    user_id=user_id,
                    user_name=user_name,
                    table_name=self.model.__tablename__,
                    record_id=record_id,
                    action=action,
                    changes_json=f"Admin {action} on {self.model.__tablename__} #{record_id}"
                )
                db.add(log)
                db.commit()
        except Exception:
            pass

    async def delete_model(self, request: Request, pk: Any) -> None:
        user_name = request.session.get("user_name") or "admin"
        user_id = request.session.get("user_id") or 1

        def _do_delete():
            with SessionLocal() as db:
                pk_val = int(pk) if str(pk).isdigit() else pk
                obj = db.query(self.model).filter(self.model.id == pk_val).first()
                if not obj:
                    return
                    
                if hasattr(obj, "soft_delete"):
                    obj.soft_delete(user_id=user_id, reason="Soft-deleted from Admin Portal")
                    action = "delete"
                elif hasattr(obj, "is_deleted"):
                    obj.is_deleted = True
                    if hasattr(obj, "deleted_at"):
                        obj.deleted_at = datetime.utcnow()
                    action = "delete"
                else:
                    db.delete(obj)
                    action = "hard_delete"

                log = AuditLog(
                    user_id=user_id,
                    user_name=user_name,
                    table_name=self.model.__tablename__,
                    record_id=int(pk_val) if isinstance(pk_val, int) else 0,
                    action=action,
                    changes_json=f"Admin deleted {self.model.__tablename__} #{pk_val}"
                )
                db.add(log)
                db.commit()

        await anyio.to_thread.run_sync(_do_delete)

# --- Category 1: IT Hardware & Devices ---

class AssetAdmin(BaseAdminView, model=Asset):
    category = "💻 Thiết bị IT (Hardware)"
    category_icon = "fa-solid fa-laptop"
    name = "Thiết bị IT"
    name_plural = "Danh mục Thiết bị IT"
    icon = "fa-solid fa-laptop"
    column_list = [
        Asset.id, Asset.asset_code, Asset.category, Asset.model,
        Asset.serial, Asset.mac_address, Asset.status, Asset.is_deleted
    ]
    column_searchable_list = [Asset.asset_code, Asset.serial, Asset.model, Asset.mac_address]
    column_sortable_list = [Asset.id, Asset.asset_code, Asset.status, Asset.is_deleted]
    column_filters = [Asset.status, Asset.is_deleted]
    form_excluded_columns = COMMON_EXCLUDED_COLUMNS + ["assignments", "license_assignments"]
    column_labels = {
        "asset_code": "Mã thiết bị",
        "category": "Loại thiết bị",
        "model": "Model thiết bị",
        "serial": "Số Serial",
        "mac_address": "Địa chỉ MAC",
        "ip_address": "Địa chỉ IP",
        "status": "Trạng thái",
        "is_deleted": "Đã xóa (Trash)",
        "note": "Ghi chú"
    }

class AssetCategoryAdmin(BaseAdminView, model=AssetCategory):
    category = "💻 Thiết bị IT (Hardware)"
    category_icon = "fa-solid fa-laptop"
    name = "Loại thiết bị"
    name_plural = "Phân loại Thiết bị"
    icon = "fa-solid fa-tags"
    column_list = [AssetCategory.id, AssetCategory.name, AssetCategory.is_deleted]
    column_searchable_list = [AssetCategory.name]
    column_filters = [AssetCategory.is_deleted]
    form_excluded_columns = COMMON_EXCLUDED_COLUMNS + ["assets"]
    column_labels = {
        "name": "Tên phân loại",
        "is_deleted": "Đã xóa (Trash)"
    }

class AssignmentAdmin(BaseAdminView, model=Assignment):
    category = "💻 Thiết bị IT (Hardware)"
    category_icon = "fa-solid fa-laptop"
    name = "Bàn giao thiết bị"
    name_plural = "Lịch sử Mượn / Bàn giao"
    icon = "fa-solid fa-handshake"
    column_list = [Assignment.id, Assignment.asset, Assignment.person, Assignment.borrowed_at, Assignment.returned_at]
    form_excluded_columns = COMMON_EXCLUDED_COLUMNS
    column_labels = {
        "asset": "Thiết bị IT",
        "person": "Người nhận",
        "borrowed_at": "Ngày bàn giao",
        "returned_at": "Ngày thu hồi",
        "note": "Ghi chú bàn giao"
    }

# --- Category 2: Software & Licensing ---

class LicenseProductAdmin(BaseAdminView, model=LicenseProduct):
    category = "🔑 Bản quyền & Phần mềm"
    category_icon = "fa-solid fa-key"
    name = "Sản phẩm phần mềm"
    name_plural = "Danh mục Phần mềm"
    icon = "fa-solid fa-cube"
    column_list = [LicenseProduct.id, LicenseProduct.name]
    column_searchable_list = [LicenseProduct.name]
    form_excluded_columns = COMMON_EXCLUDED_COLUMNS + ["licenses"]
    column_labels = {
        "name": "Tên sản phẩm phần mềm"
    }

class LicenseAdmin(BaseAdminView, model=License):
    category = "🔑 Bản quyền & Phần mềm"
    category_icon = "fa-solid fa-key"
    name = "Gói bản quyền"
    name_plural = "Bản quyền / License"
    icon = "fa-solid fa-key"
    column_list = [License.id, License.product, License.seats, License.start_date, License.expiry_date]
    form_excluded_columns = COMMON_EXCLUDED_COLUMNS + ["assignments"]
    column_labels = {
        "product": "Phần mềm",
        "seats": "Số lượng Seat",
        "start_date": "Ngày bắt đầu",
        "expiry_date": "Ngày hết hạn"
    }

class LicenseAssignmentAdmin(BaseAdminView, model=LicenseAssignment):
    category = "🔑 Bản quyền & Phần mềm"
    category_icon = "fa-solid fa-key"
    name = "Cấp phát License"
    name_plural = "Cấp phát Bản quyền"
    icon = "fa-solid fa-id-card-clip"
    column_list = [LicenseAssignment.id, LicenseAssignment.license, LicenseAssignment.asset, LicenseAssignment.person, LicenseAssignment.assigned_at, LicenseAssignment.removed_at]
    form_excluded_columns = COMMON_EXCLUDED_COLUMNS
    column_labels = {
        "license": "Gói bản quyền",
        "asset": "Thiết bị",
        "person": "Nhân viên sử dụng",
        "assigned_at": "Ngày cấp",
        "removed_at": "Ngày thu hồi"
    }

# --- Category 3: Security & Access Control ---

class AccessCardAdmin(BaseAdminView, model=AccessCard):
    category = "🛡️ An ninh & Thẻ từ"
    category_icon = "fa-solid fa-address-card"
    name = "Thẻ từ ra vào"
    name_plural = "Danh sách Thẻ từ"
    icon = "fa-solid fa-address-card"
    column_list = [AccessCard.id, AccessCard.card_no, AccessCard.is_deleted]
    column_searchable_list = [AccessCard.card_no]
    column_filters = [AccessCard.is_deleted]
    form_excluded_columns = COMMON_EXCLUDED_COLUMNS + ["loans", "room_accesses"]
    column_labels = {
        "card_no": "Mã số thẻ từ",
        "is_deleted": "Đã hủy (Trash)"
    }

class RoomAdmin(BaseAdminView, model=Room):
    category = "🛡️ An ninh & Thẻ từ"
    category_icon = "fa-solid fa-address-card"
    name = "Phòng / Khu vực"
    name_plural = "Danh sách Phòng ban / Cửa"
    icon = "fa-solid fa-door-open"
    column_list = [Room.id, Room.name]
    column_searchable_list = [Room.name]
    form_excluded_columns = COMMON_EXCLUDED_COLUMNS + ["card_accesses"]
    column_labels = {
        "name": "Tên phòng / Khu vực kiểm soát"
    }

class AccessCardRoomAdmin(BaseAdminView, model=AccessCardRoom):
    category = "🛡️ An ninh & Thẻ từ"
    category_icon = "fa-solid fa-address-card"
    name = "Quyền truy cập phòng"
    name_plural = "Phân quyền Thẻ - Phòng"
    icon = "fa-solid fa-link"
    column_list = [AccessCardRoom.id, AccessCardRoom.card, AccessCardRoom.room]
    form_excluded_columns = COMMON_EXCLUDED_COLUMNS
    column_labels = {
        "card": "Thẻ từ",
        "room": "Phòng được phép vào"
    }

class CardLoanAdmin(BaseAdminView, model=CardLoan):
    category = "🛡️ An ninh & Thẻ từ"
    category_icon = "fa-solid fa-address-card"
    name = "Mượn trả thẻ"
    name_plural = "Sổ theo dõi Mượn Thẻ"
    icon = "fa-solid fa-clock-rotate-left"
    column_list = [CardLoan.id, CardLoan.card, CardLoan.person, CardLoan.external_name, CardLoan.borrowed_at, CardLoan.returned_at]
    form_excluded_columns = COMMON_EXCLUDED_COLUMNS
    column_labels = {
        "card": "Mã thẻ",
        "person": "Nhân sự nội bộ mượn",
        "external_name": "Khách vãng lai / Thầu phụ",
        "borrowed_at": "Thời gian mượn",
        "returned_at": "Thời gian trả",
        "notes": "Mục đích mượn"
    }

# --- Category 4: Organization & Personnel ---

class DepartmentAdmin(BaseAdminView, model=Department):
    category = "🏢 Tổ chức & Nhân sự"
    category_icon = "fa-solid fa-users"
    name = "Phòng ban"
    name_plural = "Danh mục Phòng ban"
    icon = "fa-solid fa-building"
    column_list = [Department.id, Department.name_en, Department.name_ja, Department.is_deleted]
    column_searchable_list = [Department.name_en, Department.name_ja]
    column_filters = [Department.is_deleted]
    form_excluded_columns = COMMON_EXCLUDED_COLUMNS + ["members"]
    column_labels = {
        "name_en": "Tên phòng (Tiếng Anh)",
        "name_ja": "Tên phòng (Tiếng Nhật)",
        "is_deleted": "Đã xóa (Trash)"
    }

class PersonAdmin(BaseAdminView, model=Person):
    category = "🏢 Tổ chức & Nhân sự"
    category_icon = "fa-solid fa-users"
    name = "Nhân sự"
    name_plural = "Hồ sơ Nhân sự"
    icon = "fa-solid fa-users"
    column_list = [Person.id, Person.staff_code, Person.full_name, Person.department, Person.status, Person.is_deleted]
    column_searchable_list = [Person.staff_code, Person.full_name]
    column_filters = [Person.status, Person.is_deleted]
    form_excluded_columns = COMMON_EXCLUDED_COLUMNS + ["assignments", "license_assignments", "card_loans"]
    column_labels = {
        "staff_code": "Mã nhân viên",
        "full_name": "Họ và tên",
        "department": "Phòng ban",
        "status": "Trạng thái nhân sự",
        "is_deleted": "Đã xóa (Trash)"
    }

class UserAdmin(BaseAdminView, model=User):
    category = "🏢 Tổ chức & Nhân sự"
    category_icon = "fa-solid fa-users"
    name = "Tài khoản"
    name_plural = "Tài khoản & Phân quyền"
    icon = "fa-solid fa-user-shield"
    column_list = [User.id, User.username, User.full_name, User.role, User.is_active, User.created_at]
    column_searchable_list = [User.username, User.full_name]
    column_filters = [User.role, User.is_active]
    form_excluded_columns = ["created_at", "updated_at"]
    column_labels = {
        "username": "Tên đăng nhập",
        "full_name": "Họ tên hiển thị",
        "role": "Vai trò (it_admin, ga_manager, executive)",
        "is_active": "Đang hoạt động",
        "password_hash": "Mật khẩu (nhập mật khẩu mới tại đây để đổi)",
        "created_at": "Ngày tạo"
    }

    async def on_model_change(self, data: dict, model: Any, is_created: bool, request: Request) -> None:
        raw_pwd = data.get("password_hash")
        if raw_pwd and not raw_pwd.startswith("pbkdf2_sha256$"):
            data["password_hash"] = hash_password(raw_pwd)

# --- Category 5: Contracts & Governance ---

class ContractAdmin(BaseAdminView, model=Contract):
    category = "📑 Hợp đồng & Giám sát"
    category_icon = "fa-solid fa-file-contract"
    name = "Hợp đồng"
    name_plural = "Hợp đồng Mua sắm IT"
    icon = "fa-solid fa-file-contract"
    column_list = [Contract.id, Contract.code, Contract.delivery_status]
    column_searchable_list = [Contract.code]
    column_filters = [Contract.delivery_status]
    form_excluded_columns = COMMON_EXCLUDED_COLUMNS + ["lines"]
    column_labels = {
        "code": "Mã / Số hợp đồng",
        "delivery_status": "Tình trạng giao hàng"
    }

class ContractLineAdmin(BaseAdminView, model=ContractLine):
    category = "📑 Hợp đồng & Giám sát"
    category_icon = "fa-solid fa-file-contract"
    name = "Chi tiết hợp đồng"
    name_plural = "Hạng mục Hợp đồng"
    icon = "fa-solid fa-list-check"
    column_list = [ContractLine.id, ContractLine.contract, ContractLine.item_type, ContractLine.qty_ordered]
    form_excluded_columns = COMMON_EXCLUDED_COLUMNS + ["assets"]
    column_labels = {
        "contract": "Hợp đồng",
        "item_type": "Loại hạng mục (hardware, license, etc.)",
        "qty_ordered": "Số lượng đặt mua"
    }

class AuditLogAdmin(BaseAdminView, model=AuditLog):
    category = "📑 Hợp đồng & Giám sát"
    category_icon = "fa-solid fa-shield-halved"
    name = "Nhật ký kiểm toán"
    name_plural = "Audit Trail (Bất biến)"
    icon = "fa-solid fa-shield-halved"
    can_create = False
    can_edit = False
    can_delete = False
    column_list = [AuditLog.id, AuditLog.timestamp, AuditLog.user_name, AuditLog.action, AuditLog.table_name, AuditLog.record_id, AuditLog.changes_json]
    column_searchable_list = [AuditLog.table_name, AuditLog.user_name, AuditLog.action]
    column_filters = [AuditLog.action, AuditLog.table_name]
    column_labels = {
        "timestamp": "Thời gian",
        "user_name": "Tài khoản thực hiện",
        "action": "Hành động (create, update, delete, restore)",
        "table_name": "Bảng dữ liệu",
        "record_id": "ID Bản ghi",
        "changes_json": "Nội dung thay đổi"
    }

def setup_admin(app):
    admin = Admin(
        app,
        engine,
        title="Tokuyama IT Portal",
        logo_url="/static/img/logo.png",
        logo_width=180,
        logo_height=44,
        templates_dir="app/templates",
        authentication_backend=authentication_backend,
        base_url="/admin"
    )

    admin.add_view(AssetAdmin)
    admin.add_view(AssetCategoryAdmin)
    admin.add_view(AssignmentAdmin)
    
    admin.add_view(LicenseProductAdmin)
    admin.add_view(LicenseAdmin)
    admin.add_view(LicenseAssignmentAdmin)
    
    admin.add_view(AccessCardAdmin)
    admin.add_view(RoomAdmin)
    admin.add_view(AccessCardRoomAdmin)
    admin.add_view(CardLoanAdmin)
    
    admin.add_view(DepartmentAdmin)
    admin.add_view(PersonAdmin)
    admin.add_view(UserAdmin)
    
    admin.add_view(ContractAdmin)
    admin.add_view(ContractLineAdmin)
    admin.add_view(AuditLogAdmin)

    return admin
