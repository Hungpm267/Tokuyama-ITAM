"""Module đa ngôn ngữ (i18n) cho hệ thống Tokuyama Vietnam ITAM.

Hỗ trợ chuyển đổi song ngữ Tiếng Việt (vi) và Tiếng Anh (en).
Tuân thủ nguyên tắc Swiss Design: từ ngữ chuẩn mực, chính xác, không thừa thãi.
"""

from __future__ import annotations

from typing import Final
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


def translate(key: str, lang: str = DEFAULT_LANGUAGE) -> str:
    """Tra cứu bản dịch theo từ khoá và ngôn ngữ. Nếu không thấy, trả về key gốc."""
    if not key:
        return ""
    record = TRANSLATIONS.get(key)
    if record and lang in record:
        return record[lang]
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
