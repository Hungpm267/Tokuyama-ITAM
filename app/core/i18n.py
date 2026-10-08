"""Module đa ngôn ngữ (i18n) cho hệ thống Tokuyama Vietnam ITAM.

Hỗ trợ chuyển đổi song ngữ Tiếng Việt (vi) và Tiếng Anh (en).
Tuân thủ nguyên tắc Swiss Design: từ ngữ chuẩn mực, chính xác, không thừa thãi.
"""

from __future__ import annotations

from typing import Any, Final
from starlette.requests import Request

DEFAULT_LANGUAGE: Final[str] = "vi"
SUPPORTED_LANGUAGES: Final[tuple[str, ...]] = ("vi", "en", "ja")

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
    "Tìm kiếm toàn cục": {
        "vi": "Tìm kiếm toàn cục",
        "en": "Global Search",
    },
    "Thùng rác & Khôi phục": {
        "vi": "Thùng rác & Khôi phục",
        "en": "Recycle Bin",
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
    "Danh mục Phần mềm": {
        "vi": "Danh mục Phần mềm",
        "en": "Software Products",
    },
    "Kho License Phần mềm": {
        "vi": "Kho License Phần mềm",
        "en": "Software Licenses",
    },
    "Phân bổ Bản quyền": {
        "vi": "Phân bổ Bản quyền",
        "en": "License Assignments",
    },
    "Danh sách Thẻ": {
        "vi": "Danh sách Thẻ",
        "en": "Access Cards",
    },
    "Danh sách Thẻ từ": {
        "vi": "Danh sách Thẻ từ",
        "en": "Access Cards",
    },
    "Sổ Mượn-Trả Thẻ": {
        "vi": "Sổ Mượn-Trả Thẻ",
        "en": "Card Loans Log",
    },
    "Mượn thẻ từ": {
        "vi": "Mượn thẻ từ",
        "en": "Card Loan",
    },
    "Lịch sử Cho mượn Thẻ": {
        "vi": "Lịch sử Cho mượn Thẻ",
        "en": "Card Loans",
    },
    "Danh sách Hợp đồng": {
        "vi": "Danh sách Hợp đồng",
        "en": "Contracts",
    },
    "Hợp đồng Mua sắm IT": {
        "vi": "Hợp đồng Mua sắm IT",
        "en": "IT Procurement Contracts",
    },
    "Chi tiết Hạng mục": {
        "vi": "Chi tiết Hạng mục",
        "en": "Contract Line Items",
    },
    "Hạng mục Hợp đồng": {
        "vi": "Hạng mục Hợp đồng",
        "en": "Contract Lines",
    },
    "Danh bạ Nội bộ": {
        "vi": "Danh bạ Nội bộ",
        "en": "Internal Directory",
    },
    "Danh bạ & Thiết bị Điện thoại": {
        "vi": "Danh bạ & Thiết bị Điện thoại",
        "en": "Phone Directory & Devices",
    },
    "Thiết bị Thoại": {
        "vi": "Thiết bị Thoại",
        "en": "Phone Device",
    },
    "Nhật ký Hoạt động": {
        "vi": "Nhật ký Hoạt động",
        "en": "Audit Logs",
    },
    "Audit Trail (Bất biến)": {
        "vi": "Audit Trail (Bất biến)",
        "en": "Audit Trail (Immutable)",
    },
    "Nhật ký kiểm toán": {
        "vi": "Nhật ký kiểm toán",
        "en": "Audit Log",
    },
    "Ma trận Quyền Vai trò": {
        "vi": "Ma trận Quyền Vai trò",
        "en": "Role Permission Matrix",
    },
    "Quyền riêng Người dùng": {
        "vi": "Quyền riêng Người dùng",
        "en": "User Permission Overrides",
    },
    "Người đang giữ thẻ": {
        "vi": "Người đang giữ thẻ",
        "en": "Current Holder",
    },
    "Người đang giữ máy": {
        "vi": "Người đang giữ máy",
        "en": "Current Holder",
    },
    "Thao tác": {
        "vi": "Thao tác",
        "en": "Actions",
    },
    "THAO TÁC": {
        "vi": "THAO TÁC",
        "en": "ACTIONS",
    },
    "Trong kho": {
        "vi": "Trong kho",
        "en": "In Stock",
    },
    "Đang cho mượn": {
        "vi": "Đang cho mượn",
        "en": "Borrowed",
    },
    "Bị mất": {
        "vi": "Bị mất",
        "en": "Lost",
    },
    "Đã hủy": {
        "vi": "Đã hủy",
        "en": "Decommissioned",
    },
    "Đang sử dụng": {
        "vi": "Đang sử dụng",
        "en": "In Use",
    },
    "Đang làm việc": {
        "vi": "Đang làm việc",
        "en": "Active",
    },
    "Sắp vào làm": {
        "vi": "Sắp vào làm",
        "en": "Scheduled",
    },
    "Đã nghỉ việc": {
        "vi": "Đã nghỉ việc",
        "en": "Resigned",
    },
    "Đang sửa chữa": {
        "vi": "Đang sửa chữa",
        "en": "In Repair",
    },
    "Đã thanh lý": {
        "vi": "Đã thanh lý",
        "en": "Disposed",
    },
    "Đã trả": {
        "vi": "Đã trả",
        "en": "Returned",
    },
    "Đang mượn": {
        "vi": "Đang mượn",
        "en": "Borrowing",
    },
    "Đã thu hồi": {
        "vi": "Đã thu hồi",
        "en": "Returned",
    },
    "Bàn giao": {
        "vi": "Bàn giao",
        "en": "Assign",
    },
    "Thu hồi": {
        "vi": "Thu hồi",
        "en": "Return",
    },
    "Thu hồi thiết bị": {
        "vi": "Thu hồi thiết bị",
        "en": "Return Asset",
    },
    "Nhận hàng": {
        "vi": "Nhận hàng",
        "en": "Receive",
    },
    "Đã đủ hàng": {
        "vi": "Đã đủ hàng",
        "en": "Fully Delivered",
    },
    "Giao một phần": {
        "vi": "Giao một phần",
        "en": "Partial Delivery",
    },
    "Chưa nhận": {
        "vi": "Chưa nhận",
        "en": "Pending",
    },
    "Vượt định mức": {
        "vi": "Vượt định mức",
        "en": "Over Quota",
    },
    "Hết chỗ": {
        "vi": "Hết chỗ",
        "en": "Full",
    },
    "Số thẻ": {
        "vi": "Số thẻ",
        "en": "Card Number",
    },
    "Loại thẻ": {
        "vi": "Loại thẻ",
        "en": "Card Type",
    },
    "Trạng thái": {
        "vi": "Trạng thái",
        "en": "Status",
    },
    "Ghi chú": {
        "vi": "Ghi chú",
        "en": "Notes",
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
    "status_badge": {"vi": "Trạng thái", "en": "Status", "ja": "ステータス"},
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
    "current_borrower": {"vi": "Người đang giữ thẻ", "en": "Current Holder", "ja": "保持者"},
    "current_holder": {"vi": "Người đang giữ máy", "en": "Current Holder", "ja": "保持者"},
    "actions_quick": {"vi": "Thao tác", "en": "Actions", "ja": "操作"},

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
    "qty_ordered": {"vi": "Số lượng đặt mua", "en": "Ordered Quantity", "ja": "発注数量"},
    "qty_delivered": {"vi": "Số lượng đã nhận", "en": "Delivered Quantity", "ja": "納品済み数量"},
    "qty_remaining": {"vi": "Số lượng còn lại", "en": "Remaining Quantity", "ja": "残数量"},
    "delivery_progress": {"vi": "Tiến độ nhận hàng", "en": "Delivery Progress", "ja": "納品進捗"},
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
    ("access-card", "card_no"): {"vi": "Mã số thẻ từ", "en": "Card Number", "ja": "カード番号"},
    ("access-card", "card_type"): {"vi": "Phân loại thẻ", "en": "Card Type", "ja": "カード種別"},
    ("access-card", "status"): {"vi": "Trạng thái thẻ", "en": "Card Status", "ja": "カード状態"},
    ("access-card", "status_badge"): {"vi": "Trạng thái", "en": "Status", "ja": "ステータス"},
    ("access-card", "current_borrower"): {"vi": "Người đang giữ thẻ", "en": "Current Holder", "ja": "保持者"},

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

JA_TRANSLATIONS: Final[dict[str, str]] = {
    # System & Layout
    "Tokuyama IT Portal": "トクヤマITポータル",
    "IT Asset Management": "IT資産管理",
    "IT Asset Management System": "IT資産管理システム",
    "Tổng quan Quản trị": "ダッシュボード",
    "Bảng điều khiển tác nghiệp IT": "IT運用コンソール",
    "Đăng xuất": "ログアウト",
    "Đăng nhập": "ログイン",
    "QUẢN TRỊ VIÊN": "システム管理者",
    "ADMINISTRATOR": "システム管理者",
    "GA MANAGER": "総務マネージャー",
    "EXECUTIVE": "役員・経営陣",
    "ONLINE": "オンライン",
    "Online": "オンライン",

    # Sidebar Categories
    "Hệ thống & Phân quyền": "システム・権限管理",
    "Danh mục Dùng chung": "マスタ管理",
    "Nhân sự": "社員・人事",
    "Tài sản": "IT資産・機器",
    "License": "ソフトウェアライセンス",
    "Thẻ ra vào": "入退室カード",
    "Hợp đồng": "調達契約",
    "Danh bạ thoại": "内線電話帳",
    "Truy vết": "監査ログ",

    # Submenus & Model Names
    "Tài khoản Đăng nhập": "ログインアカウント",
    "Người dùng": "ユーザー",
    "Vai trò Hệ thống": "ロール設定",
    "Vai trò": "ロール",
    "Ma trận Quyền": "権限マトリクス",
    "Ma trận Quyền Vai trò": "ロール権限マトリクス",
    "Quyền vai trò": "ロール権限",
    "Ghi đè Quyền": "個別権限設定",
    "Quyền riêng Người dùng": "個別ユーザー権限",
    "Ghi đè quyền": "個別権限",
    "Danh mục Phòng ban": "部署マスタ",
    "Phòng ban": "部署",
    "Danh mục Loại tài sản": "資産分類",
    "Loại tài sản": "機器分類",
    "Danh mục Nhãn (Tags)": "機器タグ",
    "Nhãn tài sản": "機器タグ",
    "Danh mục Vị trí": "設置場所・エリア",
    "Vị trí / Phòng": "設置場所",
    "Hồ sơ Nhân sự": "社員名簿",
    "Kho Mật khẩu Nhân sự": "パスワード保管庫",
    "Mật khẩu nhân viên": "社員パスワード",
    "Danh sách Thiết bị": "機器台帳",
    "Tài sản IT": "IT機器",
    "Lịch sử Bàn giao / Thu hồi": "割当・返却履歴",
    "Lịch sử Cấp phát Tài sản": "機器割当履歴",
    "Bàn giao thiết bị": "機器割当",
    "Danh mục Sản phẩm License": "ソフトウェア製品",
    "Danh mục Phần mềm": "ソフトウェア製品一覧",
    "Sản phẩm License": "ソフトウェア製品",
    "Danh sách License": "ライセンス台帳",
    "Kho License Phần mềm": "ライセンス台帳",
    "Bản quyền License": "ソフトウェアライセンス",
    "Cấp phát License Thiết bị": "ライセンス割当",
    "Phân bổ Bản quyền": "ライセンス割当",
    "Gán License": "ライセンス割当",
    "Danh sách Thẻ": "ICカード一覧",
    "Danh sách Thẻ từ": "入退室カード一覧",
    "Sổ Mượn-Trả Thẻ": "カード貸出返却台帳",
    "Mượn thẻ từ": "カード貸出",
    "Lịch sử Cho mượn Thẻ": "カード貸出台帳",
    "Danh sách Hợp đồng": "契約一覧",
    "Hợp đồng Mua sắm IT": "調達契約一覧",
    "Chi tiết Hạng mục": "契約明細一覧",
    "Hạng mục Hợp đồng": "契約明細",
    "Danh bạ Nội bộ": "社内電話帳",
    "Danh bạ & Thiết bị Điện thoại": "内線電話・通信機器一覧",
    "Thiết bị Thoại": "内線電話機器",
    "Nhật ký Hoạt động": "システム操作ログ",
    "Audit Trail (Bất biến)": "監査ログ（改ざん防止）",
    "Nhật ký kiểm toán": "監査ログ",

    # Table Column Labels & Property Names
    "Người đang giữ thẻ": "保持者",
    "Người đang giữ máy": "保持者",
    "Thao tác": "操作",
    "THAO TÁC": "操作",
    "Số thẻ": "カード番号",
    "Loại thẻ": "カード種別",
    "Trạng thái": "ステータス",
    "Ghi chú": "備考",
    "Mục đích mượn": "利用目的",
    "Thời điểm mượn": "貸出日時",
    "Dự kiến ngày trả": "返却予定日",
    "Thời điểm trả": "返却日時",
    "Số lượng đặt mua": "発注数量",
    "Đã nhận": "納品済み",
    "Tiến độ": "進捗",

    # Status Values & Action Labels
    "Trong kho": "在庫",
    "Đang cho mượn": "貸出中",
    "Bị mất": "紛失",
    "Đã hủy": "無効化",
    "Đang sử dụng": "使用中",
    "Đang làm việc": "在籍",
    "Sắp vào làm": "入社予定",
    "Đã nghỉ việc": "退職",
    "Đang sửa chữa": "修理中",
    "Đã thanh lý": "廃棄済み",
    "Đã trả": "返却済み",
    "Đang mượn": "貸出中",
    "Đã thu hồi": "回収済み",
    "Bàn giao": "割当",
    "Thu hồi": "返却",
    "Thu hồi thiết bị": "機器返却",
    "Nhận hàng": "受入",
    "Đã đủ hàng": "完納",
    "Giao một phần": "分納",
    "Chưa nhận": "未受入",
    "Vượt định mức": "超過",
    "Hết chỗ": "空きなし",

    # UI Controls & Pagination
    "Hiển thị": "表示件数",
    "Trang": "ページ",
    "Trước": "前へ",
    "Sau": "次へ",
    "Quay lại": "戻る",
    "Quay lại danh sách": "一覧に戻る",
    "Xem chi tiết": "詳細表示",
    "+ Thêm mới": "+ 新規作成",

    # Dashboard Metrics & Units
    "Thiết bị IT": "IT機器",
    "Đang cấp phát": "割当済み",
    "Bản quyền phần mềm": "ソフトウェアライセンス",
    "máy": "台",
    "lượt": "件",
    "gói": "本",
    "thẻ": "枚",
    "người": "名",
    "hợp đồng": "件",

    # Dashboard Sections
    "Chi tiết": "詳細",
    "Nhật ký hoạt động gần nhất": "最近の操作履歴",
    "Xem tất cả nhật ký": "すべてのログを表示",
    "Mã": "ID",
    "Thời điểm": "日時",
    "Hành động": "操作",
    "Bảng dữ liệu": "テーブル",
    "Bản ghi ID": "レコードID",
    "Địa chỉ IP": "IPアドレス",
    "Tổng quan vận hành": "運用概要",
    "Tỷ lệ cấp phát": "割当率",
    "Nhân sự đang làm việc": "在籍社員",
    "Hợp đồng mua sắm": "調達契約",
    "Thẻ đang mượn": "貸出中カード",
    "Thao tác nhanh": "クイック操作",
    "Thêm thiết bị mới": "機器の新規登録",
    "Cấp phát tài sản": "機器の割当",
    "Thêm nhân sự": "社員の新規追加",
    "Cho mượn thẻ": "カード貸出",
    "Thêm danh bạ thoại": "電話番号追加",
    "Chưa có dữ liệu kiểm toán phát sinh trong phiên làm việc này.": "このセッションでの監査ログはありません。",

    # Alerts & Dialogs
    "Thẻ mượn quá hạn hẹn trả": "返却期限超過カード",
    "Sổ mượn thẻ": "カード貸出台帳",
    "Mã thẻ": "カード番号",
    "Người mượn": "借用者",
    "Hẹn trả": "返却予定日",
    "Tình trạng": "状態",
    "Trễ": "遅延",
    "ngày": "日",
    "Hiện không có thẻ nào bị quá hạn hẹn trả.": "現在、返却期限を超過したカードはありません。",
    "Bản quyền sắp hết hạn (≤ 60 ngày)": "期限間近のライセンス (60日以内)",
    "Xem tất cả": "すべて表示",
    "Phần mềm": "ソフトウェア",
    "Seat": "シート",
    "Hạn dùng": "有効期限",
    "Còn lại": "残り",
    "Đã hết hạn": "期限切れ",
    "Tất cả bản quyền đều đang trong thời hạn an toàn.": "すべてのライセンスは有効期限内です。",

    # Actions & Buttons
    "Xác nhận xóa": "削除の確認",
    "Bạn có chắc chắn muốn xóa bản ghi này?": "このレコードを削除してもよろしいですか？",
    "Lý do xóa (tùy chọn)": "削除理由（任意）",
    "Xóa": "削除",
    "Hủy": "キャンセル",
    "Xóa các mục đã chọn": "選択項目を削除",
    "Không thể xóa tài khoản của chính bạn đang đăng nhập.": "現在ログイン中の自身のアカウントは削除できません。",
    "Không thể xóa vai trò ADMIN hệ thống.": "システムADMINロールは削除できません。",
    "Chỉnh sửa": "編集",
    "Lưu": "保存",
    "Thêm mới": "新規作成",
    "Tìm kiếm": "検索",
    "Nhập kho theo lô": "一括受入・入庫",
    "Bàn giao / Thu hồi": "機器割当・返却",
    "Tìm kiếm toàn cục": "全体検索",
    "Thùng rác & Khôi phục": "ゴミ箱・データ復元",
}

JA_PROPERTY_LABELS: Final[dict[str, str]] = {
    "id": "ID",
    "created_at": "作成日時",
    "created_by": "作成者",
    "updated_at": "更新日時",
    "updated_by": "更新者",
    "is_deleted": "削除状態",
    "deleted_at": "削除日時",
    "delete_reason": "削除理由",
    "deleted_by": "削除者",
    "code": "コード",
    "name": "名称",
    "name_en": "英語/越語名",
    "name_ja": "日本語名",
    "note": "備考",
    "remarks": "追記事項",
    "status": "ステータス",
    "description": "説明",
    "color": "カラー",
    "username": "ユーザー名",
    "password_hash": "パスワードハッシュ",
    "display_name": "表示名",
    "preferred_lang": "優先言語",
    "is_active": "有効状態",
    "last_login_at": "最終ログイン日時",
    "role_id": "ロール",
    "role": "ロール",
    "user_id": "ユーザー",
    "user": "ユーザー",
    "users": "ユーザー一覧",
    "module": "機能モジュール",
    "action": "アクション",
    "granted": "権限付与",
    "permissions": "権限一覧",
    "staff_code": "社員番号",
    "user_login_id": "ログインアカウント",
    "full_name": "氏名",
    "department_id": "所属部署",
    "department": "所属部署",
    "email": "メールアドレス",
    "start_working_date": "入社日",
    "person_id": "社員",
    "person": "社員",
    "pc_password_enc": "PCパスワード（暗号化）",
    "pc_password_note": "PCパスワード備考",
    "email_password_enc": "メールパスワード（暗号化）",
    "email_password_note": "メールパスワード備考",
    "key_version": "暗号化鍵バージョン",
    "secret": "機密情報",
    "asset_code": "資産番号 (GA)",
    "vendor_code": "ベンダーコード",
    "category_id": "機器カテゴリ",
    "category": "機器カテゴリ",
    "contract_line_id": "契約明細",
    "contract_line": "契約明細",
    "model": "モデル・型番",
    "form_factor": "形状・タイプ",
    "serial": "シリアル番号",
    "hwid": "ハードウェアID",
    "mac_ethernet": "MACアドレス (LAN)",
    "mac_wifi": "MACアドレス (Wi-Fi)",
    "asset_id": "IT機器",
    "asset": "IT機器",
    "assets": "機器一覧",
    "tag_id": "資産タグ",
    "tags": "資産タグ",
    "borrowed_at": "割当・貸出日時",
    "returned_at": "返却日時",
    "assignments": "割当履歴",
    "product_id": "ソフトウェア製品",
    "product": "ソフトウェア製品",
    "license_id": "ライセンス",
    "license": "ライセンス",
    "license_key_enc": "ライセンスキー（暗号化）",
    "license_type": "ライセンス種別",
    "seats": "総ライセンス数",
    "assigned_seats": "割当済み",
    "remaining_seats": "空き",
    "start_date": "開始日",
    "expiry_date": "有効期限",
    "assigned_at": "割当日時",
    "removed_at": "回収日時",
    "status_badge": "ステータス",
    "licenses": "ライセンス一覧",
    "card_id": "ICカード",
    "card": "ICカード",
    "card_no": "カード番号",
    "card_type": "カード種別",
    "loans": "貸出履歴",
    "external_name": "外部借用者氏名",
    "external_company": "外部借用者所属会社",
    "purpose": "利用目的",
    "expected_return_at": "返却予定日",
    "location_id": "設置場所",
    "location": "設置場所",
    "building": "棟・建物",
    "floor": "階",
    "room_en": "部屋名 (英語)",
    "room_ja": "部屋名 (日本語)",
    "is_access_controlled": "入退室制限",
    "contract_id": "調達契約",
    "contract": "調達契約",
    "vendor": "ベンダー",
    "vendor_name": "ベンダー名",
    "signed_date": "契約締結日",
    "delivery_status": "納品状況",
    "item_type": "品目種別",
    "qty_ordered": "発注数量",
    "qty_delivered": "納品数量",
    "qty_remaining": "残数量",
    "delivery_progress": "納品進捗",
    "lines": "契約明細",
    "device_name": "電話機器名",
    "device_type": "電話種別",
    "extension_number": "内線番号",
    "table_name": "テーブル名",
    "record_id": "レコードID",
    "before_after": "変更履歴",
    "ip_address": "IPアドレス",
    "summary": "概要",
    "current_borrower": "保持者",
    "current_holder": "保持者",
    "actions_quick": "操作",
}

JA_MODEL_SPECIFIC_LABELS: Final[dict[tuple[str, str], str]] = {
    ("department", "code"): "部署コード",
    ("department", "name_en"): "部署名 (英語/越語)",
    ("department", "name_ja"): "部署名 (日本語)",
    ("asset-category", "name_en"): "分類名 (英語/越語)",
    ("asset-category", "name_ja"): "分類名 (日本語)",
    ("asset-tag", "code"): "タグコード",
    ("asset-tag", "name_en"): "タグ名 (英語/越語)",
    ("asset-tag", "name_ja"): "タグ名 (日本語)",
    ("asset-tag", "color"): "タグカラー",
    ("role", "code"): "ロールコード",
    ("role", "name_en"): "ロール名 (英語/越語)",
    ("role", "name_ja"): "ロール名 (日本語)",
    ("contract", "code"): "契約番号",
    ("contract", "vendor_name"): "ベンダー名",
    ("contract", "signed_date"): "契約締結日",
    ("contract", "delivery_status"): "納品状況",
    ("contract-line", "contract"): "調達契約",
    ("contract-line", "item_type"): "品目種別",
    ("contract-line", "spec"): "仕様・スペック",
    ("contract-line", "qty_ordered"): "発注数量",
    ("access-card", "card_no"): "カード番号",
    ("access-card", "card_type"): "カード種別",
    ("access-card", "status"): "カード状態",
    ("access-card", "status_badge"): "ステータス",
    ("access-card", "current_borrower"): "保持者",
    ("access-card", "note"): "備考",
    ("card-loan", "card"): "ICカード",
    ("card-loan", "borrowed_at"): "貸出日時",
    ("card-loan", "expected_return_at"): "返却予定日",
    ("card-loan", "returned_at"): "返却日時",
    ("assignment", "asset"): "対象機器",
    ("assignment", "person"): "担当社員",
    ("assignment", "borrowed_at"): "割当日時",
    ("assignment", "returned_at"): "返却日時",
    ("person", "staff_code"): "社員番号",
    ("person", "full_name"): "氏名",
    ("person", "department"): "所属部署",
    ("person", "status"): "就業状態",
    ("person", "start_working_date"): "入社日",
    ("asset", "asset_code"): "資産番号 (GA)",
    ("asset", "vendor_code"): "ベンダーコード",
    ("asset", "category"): "機器カテゴリ",
    ("asset", "model"): "モデル",
    ("asset", "serial"): "シリアル番号",
    ("asset", "status"): "機器状態",
}

# Tự động nạp dữ liệu bản dịch tiếng Nhật vào từ điển hệ thống
for _k, _v in JA_TRANSLATIONS.items():
    if _k in TRANSLATIONS:
        TRANSLATIONS[_k]["ja"] = _v
    else:
        TRANSLATIONS[_k] = {"vi": _k, "en": _k, "ja": _v}

for _k, _v in JA_PROPERTY_LABELS.items():
    if _k in PROPERTY_LABELS:
        PROPERTY_LABELS[_k]["ja"] = _v

for _k, _v in JA_MODEL_SPECIFIC_LABELS.items():
    if _k in MODEL_SPECIFIC_LABELS:
        MODEL_SPECIFIC_LABELS[_k]["ja"] = _v

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

    # Tra cứu đảo chiều theo nhãn vi, en hoặc ja trong PROPERTY_LABELS
    for rec in PROPERTY_LABELS.values():
        if key in (rec.get("vi"), rec.get("en"), rec.get("ja")):
            if lang in rec:
                return rec[lang]

    # Tra cứu đảo chiều theo MODEL_SPECIFIC_LABELS
    for rec in MODEL_SPECIFIC_LABELS.values():
        if key in (rec.get("vi"), rec.get("en"), rec.get("ja")):
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
