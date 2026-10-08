"""Module đa ngôn ngữ (i18n) cho hệ thống Tokuyama Vietnam ITAM.

Hỗ trợ chuyển đổi song ngữ Tiếng Việt (vi) và Tiếng Anh (en).
Tuân thủ nguyên tắc Swiss Design: từ ngữ chuẩn mực, chính xác, không thừa thãi.
"""

from __future__ import annotations

from typing import Any, Final
from starlette.requests import Request

DEFAULT_LANGUAGE: Final[str] = "vi"
SUPPORTED_LANGUAGES: Final[tuple[str, ...]] = ("vi", "en")

TRANSLATIONS: Final[dict[str, dict[str, str]]] = {
    # System & Layout
    "Tokuyama IT Portal": {
        "vi": "Cổng Quản trị IT Tokuyama",
        "en": "Tokuyama IT Portal",
    },
    "IT Asset Management": {
        "vi": "Quản lý Tài sản IT",
        "en": "IT Asset Management",
    },
    "IT Asset Management System": {
        "vi": "Hệ thống Quản lý Tài sản IT",
        "en": "IT Asset Management System",
    },
    "Tổng quan Quản trị": {
        "vi": "Tổng quan Quản trị",
        "en": "Dashboard",
    },
    "Bảng điều khiển tác nghiệp IT": {
        "vi": "Bảng điều khiển tác nghiệp IT",
        "en": "IT Operations Console",
    },
    "Đăng xuất": {
        "vi": "Đăng xuất",
        "en": "Sign Out",
    },
    "QUẢN TRỊ VIÊN": {
        "vi": "QUẢN TRỊ VIÊN",
        "en": "ADMINISTRATOR",
    },
    "ADMINISTRATOR": {
        "vi": "QUẢN TRỊ VIÊN",
        "en": "ADMINISTRATOR",
    },
    "ONLINE": {
        "vi": "ONLINE",
        "en": "ONLINE",
    },

    # Sidebar Categories
    "Hệ thống & Phân quyền": {
        "vi": "Hệ thống & Phân quyền",
        "en": "System & RBAC",
    },
    "Danh mục Dùng chung": {
        "vi": "Danh mục Dùng chung",
        "en": "Master Data",
    },
    "Nhân sự": {
        "vi": "Nhân sự",
        "en": "Personnel",
    },
    "Tài sản": {
        "vi": "Tài sản",
        "en": "Hardware Assets",
    },
    "License": {
        "vi": "License",
        "en": "Software Licenses",
    },
    "Thẻ ra vào": {
        "vi": "Thẻ ra vào",
        "en": "Access Cards",
    },
    "Hợp đồng": {
        "vi": "Hợp đồng",
        "en": "Contracts",
    },
    "Danh bạ thoại": {
        "vi": "Danh bạ thoại",
        "en": "Phone Directory",
    },
    "Truy vết": {
        "vi": "Truy vết",
        "en": "Audit Logs",
    },

    # Submenus & Model Names
    "Tài khoản Đăng nhập": {
        "vi": "Tài khoản Đăng nhập",
        "en": "User Accounts",
    },
    "Người dùng": {
        "vi": "Người dùng",
        "en": "Users",
    },
    "Vai trò Hệ thống": {
        "vi": "Vai trò Hệ thống",
        "en": "System Roles",
    },
    "Ma trận Quyền": {
        "vi": "Ma trận Quyền",
        "en": "Role Permissions",
    },
    "Ghi đè Quyền": {
        "vi": "Ghi đè Quyền",
        "en": "Permission Overrides",
    },
    "Danh mục Phòng ban": {
        "vi": "Danh mục Phòng ban",
        "en": "Departments",
    },
    "Danh mục Loại tài sản": {
        "vi": "Danh mục Loại tài sản",
        "en": "Asset Categories",
    },
    "Danh mục Nhãn (Tags)": {
        "vi": "Danh mục Nhãn (Tags)",
        "en": "Asset Tags",
    },
    "Danh mục Vị trí": {
        "vi": "Danh mục Vị trí",
        "en": "Locations",
    },
    "Hồ sơ Nhân sự": {
        "vi": "Hồ sơ Nhân sự",
        "en": "Employee Records",
    },
    "Kho Mật khẩu Nhân sự": {
        "vi": "Kho Mật khẩu Nhân sự",
        "en": "Secret Vault",
    },
    "Danh sách Thiết bị": {
        "vi": "Danh sách Thiết bị",
        "en": "Hardware Assets",
    },
    "Lịch sử Cấp phát Tài sản": {
        "vi": "Lịch sử Cấp phát Tài sản",
        "en": "Asset Assignments",
    },
    "Danh mục Sản phẩm License": {
        "vi": "Danh mục Sản phẩm License",
        "en": "License Products",
    },
    "Danh sách License": {
        "vi": "Danh sách License",
        "en": "Software Licenses",
    },
    "Cấp phát License Thiết bị": {
        "vi": "Cấp phát License Thiết bị",
        "en": "License Assignments",
    },
    "Danh sách Thẻ": {
        "vi": "Danh sách Thẻ",
        "en": "Access Cards",
    },
    "Lịch sử Cho mượn Thẻ": {
        "vi": "Lịch sử Cho mượn Thẻ",
        "en": "Card Loans",
    },
    "Danh sách Hợp đồng": {
        "vi": "Danh sách Hợp đồng",
        "en": "Contracts",
    },
    "Hạng mục Hợp đồng": {
        "vi": "Hạng mục Hợp đồng",
        "en": "Contract Lines",
    },
    "Danh bạ Nội bộ": {
        "vi": "Danh bạ Nội bộ",
        "en": "Internal Directory",
    },
    "Nhật ký Hoạt động": {
        "vi": "Nhật ký Hoạt động",
        "en": "Audit Logs",
    },

    # Dashboard Metrics & Units
    "Thiết bị IT": {
        "vi": "Thiết bị IT",
        "en": "Hardware Assets",
    },
    "Đang cấp phát": {
        "vi": "Đang cấp phát",
        "en": "Active Assignments",
    },
    "Bản quyền phần mềm": {
        "vi": "Bản quyền phần mềm",
        "en": "Software Licenses",
    },
    "máy": {
        "vi": "máy",
        "en": "units",
    },
    "lượt": {
        "vi": "lượt",
        "en": "active",
    },
    "gói": {
        "vi": "gói",
        "en": "licenses",
    },
    "thẻ": {
        "vi": "thẻ",
        "en": "cards",
    },
    "người": {
        "vi": "người",
        "en": "staff",
    },
    "hợp đồng": {
        "vi": "hợp đồng",
        "en": "contracts",
    },

    # Dashboard Sections
    "Chi tiết": {
        "vi": "Chi tiết",
        "en": "Details",
    },
    "Nhật ký hoạt động gần nhất": {
        "vi": "Nhật ký hoạt động gần nhất",
        "en": "Recent Activity Log",
    },
    "Xem tất cả nhật ký": {
        "vi": "Xem tất cả nhật ký",
        "en": "View all audit logs",
    },
    "Mã": {
        "vi": "Mã",
        "en": "ID",
    },
    "Thời điểm": {
        "vi": "Thời điểm",
        "en": "Timestamp",
    },
    "Hành động": {
        "vi": "Hành động",
        "en": "Action",
    },
    "Bảng dữ liệu": {
        "vi": "Bảng dữ liệu",
        "en": "Table",
    },
    "Bản ghi ID": {
        "vi": "Bản ghi ID",
        "en": "Record ID",
    },
    "Địa chỉ IP": {
        "vi": "Địa chỉ IP",
        "en": "IP Address",
    },
    "Tổng quan vận hành": {
        "vi": "Tổng quan vận hành",
        "en": "Operational Summary",
    },
    "Tỷ lệ cấp phát": {
        "vi": "Tỷ lệ cấp phát",
        "en": "Allocation Rate",
    },
    "Nhân sự đang làm việc": {
        "vi": "Nhân sự đang làm việc",
        "en": "Active Personnel",
    },
    "Hợp đồng mua sắm": {
        "vi": "Hợp đồng mua sắm",
        "en": "Procurement Contracts",
    },
    "Thẻ đang mượn": {
        "vi": "Thẻ đang mượn",
        "en": "Cards on Loan",
    },
    "Thao tác nhanh": {
        "vi": "Thao tác nhanh",
        "en": "Quick Actions",
    },
    "Thêm thiết bị mới": {
        "vi": "Thêm thiết bị mới",
        "en": "New Hardware Asset",
    },
    "Cấp phát tài sản": {
        "vi": "Cấp phát tài sản",
        "en": "New Assignment",
    },
    "Thêm nhân sự": {
        "vi": "Thêm nhân sự",
        "en": "New Employee",
    },
    "Cho mượn thẻ": {
        "vi": "Cho mượn thẻ",
        "en": "New Card Loan",
    },
    "Chưa có dữ liệu kiểm toán phát sinh trong phiên làm việc này.": {
        "vi": "Chưa có dữ liệu kiểm toán phát sinh trong phiên làm việc này.",
        "en": "No audit trail records recorded in this session.",
    },
    "Xác nhận xóa": {
        "vi": "Xác nhận xóa",
        "en": "Confirm Deletion",
    },
    "Bạn có chắc chắn muốn xóa bản ghi này?": {
        "vi": "Bạn có chắc chắn muốn xóa bản ghi này?",
        "en": "Are you sure you want to delete this record?",
    },
    "Lý do xóa (tùy chọn)": {
        "vi": "Lý do xóa (tùy chọn)",
        "en": "Deletion reason (optional)",
    },
    "Xóa": {
        "vi": "Xóa",
        "en": "Delete",
    },
    "Hủy": {
        "vi": "Hủy",
        "en": "Cancel",
    },
    "Xóa các mục đã chọn": {
        "vi": "Xóa các mục đã chọn",
        "en": "Delete selected items",
    },
    "Không thể xóa tài khoản của chính bạn đang đăng nhập.": {
        "vi": "Không thể xóa tài khoản của chính bạn đang đăng nhập.",
        "en": "Cannot delete your own currently logged-in account.",
    },
    "Không thể xóa vai trò ADMIN hệ thống.": {
        "vi": "Không thể xóa vai trò ADMIN hệ thống.",
        "en": "Cannot delete the system ADMIN role.",
    },
}

# =============================================================================
# TỪ ĐIỂN TÊN THUỘC TÍNH / TRƯỜNG DỮ LIỆU THÂN THIỆN VỚI NGƯỜI DÙNG (PROPERTY LABELS)
# Giúp giao diện (details, list, form) không bao giờ hiển thị raw column name.
# =============================================================================

PROPERTY_LABELS: Final[dict[str, dict[str, str]]] = {
    # System metadata & Audit
    "id": {"vi": "Mã định danh (ID)", "en": "ID"},
    "created_at": {"vi": "Thời gian tạo", "en": "Created At"},
    "created_by": {"vi": "Người tạo", "en": "Created By"},
    "updated_at": {"vi": "Thời gian cập nhật", "en": "Updated At"},
    "updated_by": {"vi": "Người cập nhật", "en": "Updated By"},
    "is_deleted": {"vi": "Trạng thái xóa", "en": "Soft Deleted Status"},
    "deleted_at": {"vi": "Thời gian xóa", "en": "Deleted At"},
    "delete_reason": {"vi": "Lý do xóa", "en": "Deletion Reason"},
    "deleted_by": {"vi": "Người xóa", "en": "Deleted By"},

    # Common & Master data
    "code": {"vi": "Mã", "en": "Code"},
    "name": {"vi": "Tên", "en": "Name"},
    "name_en": {"vi": "Tên (Tiếng Anh/Việt)", "en": "Name (EN/VI)"},
    "name_ja": {"vi": "Tên (Tiếng Nhật)", "en": "Name (JA)"},
    "note": {"vi": "Ghi chú", "en": "Notes"},
    "remarks": {"vi": "Ghi chú bổ sung", "en": "Remarks"},
    "status": {"vi": "Trạng thái", "en": "Status"},
    "description": {"vi": "Mô tả", "en": "Description"},
    "color": {"vi": "Màu sắc", "en": "Color"},

    # Users & Auth & RBAC
    "username": {"vi": "Tên đăng nhập", "en": "Username"},
    "password_hash": {"vi": "Mật khẩu (băm)", "en": "Password Hash"},
    "display_name": {"vi": "Tên hiển thị", "en": "Display Name"},
    "preferred_lang": {"vi": "Ngôn ngữ ưa thích", "en": "Preferred Language"},
    "is_active": {"vi": "Trạng thái hoạt động", "en": "Active Status"},
    "last_login_at": {"vi": "Đăng nhập lần cuối", "en": "Last Login At"},
    "role_id": {"vi": "Vai trò hệ thống", "en": "System Role"},
    "role": {"vi": "Vai trò hệ thống", "en": "System Role"},
    "user_id": {"vi": "Người dùng", "en": "User"},
    "user": {"vi": "Người dùng", "en": "User"},
    "users": {"vi": "Danh sách người dùng", "en": "Users"},
    "module": {"vi": "Phân hệ nghiệp vụ", "en": "Business Module"},
    "action": {"vi": "Thao tác", "en": "Action"},
    "granted": {"vi": "Cấp quyền", "en": "Granted"},
    "permissions": {"vi": "Danh sách quyền", "en": "Permissions"},

    # Person / Employee & Secrets
    "staff_code": {"vi": "Mã nhân viên", "en": "Staff Code"},
    "user_login_id": {"vi": "Tài khoản đăng nhập", "en": "Login Account"},
    "full_name": {"vi": "Họ và tên", "en": "Full Name"},
    "department_id": {"vi": "Phòng ban", "en": "Department"},
    "department": {"vi": "Phòng ban", "en": "Department"},
    "email": {"vi": "Hộp thư điện tử (Email)", "en": "Email"},
    "start_working_date": {"vi": "Ngày vào làm việc", "en": "Start Working Date"},
    "person_id": {"vi": "Nhân sự", "en": "Employee"},
    "person": {"vi": "Nhân sự", "en": "Employee"},
    "pc_password_enc": {"vi": "Mật khẩu PC (Mã hóa)", "en": "PC Password (Encrypted)"},
    "pc_password_note": {"vi": "Ghi chú mật khẩu PC", "en": "PC Password Notes"},
    "email_password_enc": {"vi": "Mật khẩu Email (Mã hóa)", "en": "Email Password (Encrypted)"},
    "email_password_note": {"vi": "Ghi chú mật khẩu Email", "en": "Email Password Notes"},
    "key_version": {"vi": "Phiên bản khóa mã hóa", "en": "Key Version"},
    "secret": {"vi": "Mật khẩu bảo mật", "en": "Secrets"},

    # IT Assets & Assignments
    "asset_code": {"vi": "Mã tài sản (GA)", "en": "Asset Code (GA)"},
    "vendor_code": {"vi": "Mã tài sản (Vendor)", "en": "Vendor Code"},
    "category_id": {"vi": "Loại tài sản", "en": "Asset Category"},
    "category": {"vi": "Loại tài sản", "en": "Asset Category"},
    "contract_line_id": {"vi": "Hạng mục hợp đồng", "en": "Contract Line"},
    "contract_line": {"vi": "Hạng mục hợp đồng", "en": "Contract Line"},
    "model": {"vi": "Dòng máy (Model)", "en": "Model"},
    "form_factor": {"vi": "Kiểu dáng thiết bị", "en": "Form Factor"},
    "serial": {"vi": "Số Serial", "en": "Serial Number"},
    "hwid": {"vi": "Mã định danh phần cứng (HWID)", "en": "Hardware ID"},
    "mac_ethernet": {"vi": "Địa chỉ MAC LAN", "en": "MAC Address (LAN)"},
    "mac_wifi": {"vi": "Địa chỉ MAC Wi-Fi", "en": "MAC Address (Wi-Fi)"},
    "asset_id": {"vi": "Thiết bị tài sản", "en": "Hardware Asset"},
    "asset": {"vi": "Thiết bị tài sản", "en": "Hardware Asset"},
    "assets": {"vi": "Danh sách thiết bị", "en": "Assets"},
    "tag_id": {"vi": "Nhãn tài sản", "en": "Asset Tag"},
    "tags": {"vi": "Nhãn tài sản (Tags)", "en": "Asset Tags"},
    "borrowed_at": {"vi": "Thời điểm giao máy", "en": "Borrowed At"},
    "returned_at": {"vi": "Thời điểm thu hồi", "en": "Returned At"},
    "assignments": {"vi": "Lịch sử cấp phát", "en": "Assignments"},

    # Software Licenses
    "product_id": {"vi": "Sản phẩm phần mềm", "en": "Software Product"},
    "product": {"vi": "Sản phẩm phần mềm", "en": "Software Product"},
    "license_id": {"vi": "Bản quyền phần mềm", "en": "Software License"},
    "license": {"vi": "Bản quyền phần mềm", "en": "Software License"},
    "license_key_enc": {"vi": "License Key (Mã hóa)", "en": "License Key (Encrypted)"},
    "license_type": {"vi": "Loại bản quyền", "en": "License Type"},
    "seats": {"vi": "Tổng số bản quyền (Seats)", "en": "Total Seats", "ja": "総ライセンス数"},
    "assigned_seats": {"vi": "Đã cấp phát", "en": "Assigned Seats", "ja": "割当済み"},
    "remaining_seats": {"vi": "Còn trống", "en": "Available Seats", "ja": "空き"},
    "start_date": {"vi": "Ngày kích hoạt", "en": "Start Date"},
    "expiry_date": {"vi": "Ngày hết hạn", "en": "Expiry Date"},
    "assigned_at": {"vi": "Thời điểm cấp phát", "en": "Assigned At"},
    "removed_at": {"vi": "Thời điểm thu hồi", "en": "Revoked At"},
    "licenses": {"vi": "Danh sách bản quyền", "en": "Licenses"},

    # Access Cards & Loans
    "card_id": {"vi": "Thẻ ra vào", "en": "Access Card"},
    "card": {"vi": "Thẻ ra vào", "en": "Access Card"},
    "card_no": {"vi": "Mã số thẻ từ", "en": "Card Number"},
    "card_type": {"vi": "Loại thẻ", "en": "Card Type"},
    "loans": {"vi": "Lịch sử mượn thẻ", "en": "Card Loans"},
    "external_name": {"vi": "Người mượn ngoài", "en": "External Borrower"},
    "external_company": {"vi": "Công ty / Đơn vị ngoài", "en": "External Company"},
    "purpose": {"vi": "Mục đích sử dụng", "en": "Purpose"},
    "expected_return_at": {"vi": "Dự kiến ngày trả", "en": "Expected Return Date"},

    # Location & Facility
    "location_id": {"vi": "Vị trí / Phòng", "en": "Location"},
    "location": {"vi": "Vị trí / Phòng", "en": "Location"},
    "building": {"vi": "Tòa nhà", "en": "Building"},
    "floor": {"vi": "Tầng", "en": "Floor"},
    "room_en": {"vi": "Phòng (Tiếng Anh)", "en": "Room (EN)"},
    "room_ja": {"vi": "Phòng (Tiếng Nhật)", "en": "Room (JA)"},
    "is_access_controlled": {"vi": "Kiểm soát cửa thẻ từ", "en": "Access Controlled"},

    # Contracts & Procurement
    "contract_id": {"vi": "Hợp đồng", "en": "Contract"},
    "contract": {"vi": "Hợp đồng", "en": "Contract"},
    "vendor": {"vi": "Nhà cung cấp", "en": "Vendor"},
    "vendor_name": {"vi": "Nhà cung cấp", "en": "Vendor Name"},
    "signed_date": {"vi": "Ngày ký hợp đồng", "en": "Signed Date"},
    "delivery_status": {"vi": "Trạng thái giao hàng", "en": "Delivery Status"},
    "item_type": {"vi": "Hạng mục hàng hóa", "en": "Item Type"},
    "spec": {"vi": "Thông số kỹ thuật", "en": "Specifications"},
    "qty_ordered": {"vi": "Số lượng đặt mua", "en": "Ordered Quantity"},
    "lines": {"vi": "Các hạng mục hợp đồng", "en": "Contract Lines"},

    # Phone Directory
    "device_name": {"vi": "Tên máy điện thoại", "en": "Device Name"},
    "device_type": {"vi": "Loại điện thoại", "en": "Device Type"},
    "extension_number": {"vi": "Số máy nhánh (Ext)", "en": "Extension Number"},

    # Audit Logs
    "table_name": {"vi": "Bảng dữ liệu", "en": "Table Name"},
    "record_id": {"vi": "Mã ID bản ghi", "en": "Record ID"},
    "before_after": {"vi": "Chi tiết thay đổi", "en": "Change Details"},
    "ip_address": {"vi": "Địa chỉ IP", "en": "IP Address"},
    "summary": {"vi": "Tóm tắt kiểm toán", "en": "Summary"},
}

MODEL_SPECIFIC_LABELS: Final[dict[tuple[str, str], dict[str, str]]] = {
    # Department
    ("department", "code"): {"vi": "Mã phòng ban", "en": "Department Code"},
    ("department", "name_en"): {"vi": "Tên phòng ban (Tiếng Anh/Việt)", "en": "Department Name (EN/VI)"},
    ("department", "name_ja"): {"vi": "Tên phòng ban (Tiếng Nhật)", "en": "Department Name (JA)"},

    # Asset Category
    ("asset-category", "name_en"): {"vi": "Tên loại tài sản (Tiếng Anh/Việt)", "en": "Category Name (EN/VI)"},
    ("asset-category", "name_ja"): {"vi": "Tên loại tài sản (Tiếng Nhật)", "en": "Category Name (JA)"},

    # Asset Tag
    ("asset-tag", "code"): {"vi": "Mã nhãn", "en": "Tag Code"},
    ("asset-tag", "name_en"): {"vi": "Tên nhãn (Tiếng Anh/Việt)", "en": "Tag Name (EN/VI)"},
    ("asset-tag", "name_ja"): {"vi": "Tên nhãn (Tiếng Nhật)", "en": "Tag Name (JA)"},
    ("asset-tag", "color"): {"vi": "Màu nhãn", "en": "Tag Color"},

    # Role
    ("role", "code"): {"vi": "Mã vai trò", "en": "Role Code"},
    ("role", "name_en"): {"vi": "Tên vai trò (Tiếng Anh/Việt)", "en": "Role Name (EN/VI)"},
    ("role", "name_ja"): {"vi": "Tên vai trò (Tiếng Nhật)", "en": "Role Name (JA)"},

    # Contract
    ("contract", "code"): {"vi": "Số hợp đồng", "en": "Contract Code"},
    ("contract", "vendor_name"): {"vi": "Nhà cung cấp", "en": "Vendor Name"},
    ("contract", "signed_date"): {"vi": "Ngày ký hợp đồng", "en": "Signed Date"},
    ("contract", "delivery_status"): {"vi": "Tiến độ giao hàng", "en": "Delivery Status"},

    # Contract Line
    ("contract-line", "contract"): {"vi": "Hợp đồng", "en": "Contract"},
    ("contract-line", "item_type"): {"vi": "Hạng mục hàng hóa", "en": "Item Type"},
    ("contract-line", "spec"): {"vi": "Thông số kỹ thuật", "en": "Specifications"},
    ("contract-line", "qty_ordered"): {"vi": "Số lượng đặt mua", "en": "Quantity Ordered"},

    # Access Card
    ("access-card", "card_no"): {"vi": "Mã số thẻ từ", "en": "Card Number"},
    ("access-card", "card_type"): {"vi": "Phân loại thẻ", "en": "Card Type"},
    ("access-card", "status"): {"vi": "Trạng thái thẻ", "en": "Card Status"},

    # Card Loan
    ("card-loan", "card"): {"vi": "Thẻ mượn", "en": "Access Card"},
    ("card-loan", "borrowed_at"): {"vi": "Thời điểm mượn thẻ", "en": "Borrowed At"},
    ("card-loan", "expected_return_at"): {"vi": "Dự kiến ngày trả", "en": "Expected Return Date"},
    ("card-loan", "returned_at"): {"vi": "Thời điểm trả thẻ", "en": "Returned At"},

    # Assignment
    ("assignment", "asset"): {"vi": "Thiết bị cấp phát", "en": "Assigned Asset"},
    ("assignment", "person"): {"vi": "Nhân viên nhận máy", "en": "Assigned Employee"},
    ("assignment", "borrowed_at"): {"vi": "Thời điểm cấp phát", "en": "Assignment Date"},
    ("assignment", "returned_at"): {"vi": "Thời điểm thu hồi", "en": "Return Date"},

    # Person
    ("person", "staff_code"): {"vi": "Mã nhân viên", "en": "Staff Code"},
    ("person", "full_name"): {"vi": "Họ và tên nhân viên", "en": "Employee Full Name"},
    ("person", "department"): {"vi": "Phòng ban", "en": "Department"},
    ("person", "status"): {"vi": "Tình trạng công tác", "en": "Employment Status"},
    ("person", "start_working_date"): {"vi": "Ngày vào làm việc", "en": "Start Date"},

    # Asset
    ("asset", "asset_code"): {"vi": "Mã tài sản (GA)", "en": "Asset Code (GA)"},
    ("asset", "vendor_code"): {"vi": "Mã tài sản (Vendor)", "en": "Vendor Code"},
    ("asset", "category"): {"vi": "Loại thiết bị", "en": "Asset Category"},
    ("asset", "model"): {"vi": "Dòng máy (Model)", "en": "Model"},
    ("asset", "serial"): {"vi": "Số Serial máy", "en": "Serial Number"},
    ("asset", "status"): {"vi": "Trạng thái thiết bị", "en": "Asset Status"},
}

DEFAULT_ADMIN_COLUMN_LABELS: Final[dict[str, str]] = {
    prop: labels["vi"] for prop, labels in PROPERTY_LABELS.items()
}


def get_property_label(model_view_or_identity: Any, prop_name: str, lang: str = DEFAULT_LANGUAGE) -> str:
    """Trả về nhãn thân thiện với người dùng cho thuộc tính/cột dữ liệu thay vì database column name."""
    if not prop_name:
        return ""

    identity = ""
    if hasattr(model_view_or_identity, "identity"):
        identity = str(model_view_or_identity.identity)
    elif isinstance(model_view_or_identity, str):
        identity = model_view_or_identity

    # 1. Kiểm tra cấu hình cụ thể theo model (identity, prop_name)
    if identity and (identity, prop_name) in MODEL_SPECIFIC_LABELS:
        rec = MODEL_SPECIFIC_LABELS[(identity, prop_name)]
        if lang in rec:
            return rec[lang]

    # 2. Kiểm tra từ điển thuộc tính toàn cục (PROPERTY_LABELS) theo ngôn ngữ yêu cầu
    if prop_name in PROPERTY_LABELS:
        rec = PROPERTY_LABELS[prop_name]
        if lang in rec:
            return rec[lang]

    # 3. Kiểm tra custom column_labels của class view
    cls_labels = getattr(type(model_view_or_identity), "column_labels", None)
    if cls_labels and prop_name in cls_labels:
        lbl = cls_labels[prop_name]
        return translate(str(lbl), lang)

    if hasattr(model_view_or_identity, "_column_labels") and model_view_or_identity._column_labels:
        lbl = model_view_or_identity._column_labels.get(prop_name)
        if lbl:
            return translate(str(lbl), lang)

    # 4. Tra cứu từ điển dịch tổng quát TRANSLATIONS
    trans = translate(prop_name, lang)
    if trans != prop_name:
        return trans

    # 5. Fallback: chuyển snake_case thành Title Case thay vì giữ nguyên raw
    return prop_name.replace("_", " ").title()


def format_datetime_clean(val: Any) -> str:
    """Định dạng ngày giờ sạch sẽ (YYYY-MM-DD HH:mm:ss) thay vì hiển thị microsecond/timezone dài dòng."""
    if val is None or val == "":
        return "-"
    if hasattr(val, "strftime"):
        return val.strftime("%Y-%m-%d %H:%M:%S")
    s = str(val)
    if "T" in s or ("-" in s and ":" in s):
        # Cắt bỏ microseconds nếu có
        parts = s.replace("T", " ").split(".")
        return parts[0]
    return s


def translate(key: str, lang: str = DEFAULT_LANGUAGE) -> str:
    """Tra cứu bản dịch theo từ khoá và ngôn ngữ. Nếu không thấy, trả về key gốc."""
    if not key:
        return ""
    record = TRANSLATIONS.get(key)
    if record and lang in record:
        return record[lang]

    # Tra cứu bổ sung trong PROPERTY_LABELS theo prop_name
    if key in PROPERTY_LABELS:
        rec = PROPERTY_LABELS[key]
        if lang in rec:
            return rec[lang]

    # Tra cứu đảo chiều theo nhãn vi hoặc en trong PROPERTY_LABELS
    for rec in PROPERTY_LABELS.values():
        if key in (rec.get("vi"), rec.get("en")):
            if lang in rec:
                return rec[lang]

    # Tra cứu đảo chiều theo MODEL_SPECIFIC_LABELS
    for rec in MODEL_SPECIFIC_LABELS.values():
        if key in (rec.get("vi"), rec.get("en")):
            if lang in rec:
                return rec[lang]

    return key


def get_current_lang(request: Request) -> str:
    """Xác định ngôn ngữ hiện thời của phiên làm việc từ query, cookie hoặc session."""
    # 1. Query parameter
    lang = request.query_params.get("lang")
    if lang in SUPPORTED_LANGUAGES:
        return lang

    # 2. Cookie (lựa chọn chủ động của trình duyệt)
    cookie_lang = request.cookies.get("itam_lang")
    if cookie_lang in SUPPORTED_LANGUAGES:
        return cookie_lang

    # 3. Session
    if hasattr(request, "session"):
        session_lang = request.session.get("lang")
        if session_lang in SUPPORTED_LANGUAGES:
            return session_lang

    return DEFAULT_LANGUAGE
