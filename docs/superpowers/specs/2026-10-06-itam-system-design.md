# Hệ thống Quản lý Tài sản IT (ITAM) – Tokuyama Vietnam: Tài liệu Thiết kế Kỹ thuật (Technical Design Spec)

* **Ngày lập:** 2026-10-06
* **Dự án:** Hệ thống Quản lý Tài sản IT (ITAM) – Tokuyama Vietnam (TVC)
* **Tác giả:** Antigravity (AI Assistant) & IT Tokuyama Vietnam
* **Trạng thái:** Approved by User

---

## 1. Tóm tắt Hệ thống & Mục tiêu (Executive Summary)

Hệ thống Quản lý Tài sản IT (ITAM) là ứng dụng web nội bộ nhằm thay thế hoàn toàn các file và sheet Excel phân mảnh hiện tại tại Tokuyama Vietnam. Hệ thống đóng vai trò là nguồn dữ liệu duy nhất (Single Source of Truth) phục vụ 5 người dùng chính (1 IT Admin, 1 GA Manager, 3 Giám đốc người Nhật), quản lý thông tin nhân sự, thiết bị IT, lịch sử mượn-trả, bản quyền phần mềm (license), thẻ từ ra vào văn phòng và hợp đồng mua sắm thiết bị.

### 1.1. Mục tiêu cốt lõi
* **Tập trung hóa:** 0 file Excel quản lý tài sản sau ngày go-live (cut-over).
* **Tra cứu tức thì:** Thời gian tra cứu "thiết bị X đang ở đâu, ai giữ" dưới 5 giây (vượt chuẩn BRD < 30 giây).
* **Truy vết 100%:** Mọi biến động tài sản, license, thẻ mượn đều lưu lịch sử giao dịch và Audit Log bất biến.
* **Bảo mật tuyệt đối:** 0 mật khẩu máy tính/email lưu trong hệ thống; che mờ bản quyền đối với người dùng không phải IT Admin.

---

## 2. Kiến trúc & Công nghệ (Architecture & Tech Stack)

* **Backend Framework:** Django (Bản LTS mới nhất), kiến trúc Monolith tinh gọn, Server-Side Rendering.
* **Giao diện (UI):** Django Admin Native mở rộng. Tích hợp thanh chuyển đổi ngôn ngữ (EN/JA), chế độ Dark/Light mode tự động theo hệ điều hành, bố cục thân thiện kế thừa từ `admin/base_site.html`.
* **Cơ sở dữ liệu:** PostgreSQL (PostgreSQL 18 local cho môi trường phát triển; hỗ trợ kết nối PostgreSQL Cloud SSL qua biến môi trường `DATABASE_URL`).
* **Audit Trail:** Thư viện `django-auditlog` ghi nhận tự động thay đổi (JSON diff) và bảng quản trị Audit Log bất biến (chỉ đọc).
* **Quản lý cấu hình:** `python-dotenv` thông qua tệp `.env`.
* **Đa ngôn ngữ (i18n):** Django i18n với tiếng Anh (`en` - mặc định) và tiếng Nhật (`ja`), cấu trúc tệp `.po` sẵn sàng bổ sung tiếng Việt (`vi`).

---

## 3. Cấu trúc Dự án (Project Organization)

Dự án được phân rã thành các ứng dụng (Django apps) độc lập, có trách nhiệm rõ ràng:

```
toku-app/
├── manage.py
├── toku_itam/                 # Cấu hình chính của project
│   ├── __init__.py
│   ├── asgi.py
│   ├── settings.py           # Cấu hình base, đọc từ .env
│   ├── urls.py               # Định tuyến chính & gắn Admin
│   └── wsgi.py
├── core/                     # Hạ tầng chung
│   ├── models.py             # TimeStampedModel, SoftDeleteModel, Custom Managers
│   ├── middleware.py         # Thread-local middleware lấy current user cho Soft Delete & Audit
│   ├── admin.py              # Custom AdminSite, DashboardView, GlobalSearchView, TrashAdmin
│   ├── management/
│   │   └── commands/
│   │       └── init_system.py # Lệnh khởi tạo RBAC, admin user và seed data
│   └── templates/
│       └── admin/            # Tùy biến template admin (Dashboard, Search, Person Profile)
├── apps/
│   ├── organization/         # Quản lý Phòng ban & Nhân viên
│   │   ├── models.py         # Department, Person
│   │   └── admin.py
│   ├── assets/               # Quản lý Thiết bị & Lịch sử mượn trả
│   │   ├── models.py         # AssetCategory, Asset, Assignment
│   │   └── admin.py
│   ├── licenses/             # Quản lý License phần mềm & Gán bản quyền
│   │   ├── models.py         # LicenseProduct, License, LicenseAssignment
│   │   └── admin.py
│   ├── cards/                # Quản lý Thẻ từ, Phòng truy cập & Lịch sử mượn
│   │   ├── models.py         # Room, AccessCard, AccessCardRoom, CardLoan
│   │   └── admin.py
│   └── contracts/            # Quản lý Hợp đồng & Dòng hàng
│       ├── models.py         # Contract, ContractLine
│       └── admin.py
├── locale/                   # Tệp dịch đa ngôn ngữ (.po, .mo)
├── docs/                     # Tài liệu & Specs
└── tests/                    # Bộ kiểm thử tự động (Unit & Integration tests)
```

---

## 4. Mô hình Dữ liệu Chi tiết (Data Models & 15 Tables)

### 4.1. Lớp Cơ sở (Abstract Base Models)

Mọi bảng nghiệp vụ đều kế thừa từ `SoftDeleteModel` (bao gồm `TimeStampedModel`):
* `created_at` (DateTimeField, auto_now_add=True)
* `created_by` (ForeignKey to `auth.User`, null=True, on_delete=SET_NULL, related_name='+')
* `updated_at` (DateTimeField, auto_now=True)
* `updated_by` (ForeignKey to `auth.User`, null=True, on_delete=SET_NULL, related_name='+')
* `is_deleted` (BooleanField, default=False, db_index=True)
* `deleted_at` (DateTimeField, null=True, blank=True)
* `deleted_by` (ForeignKey to `auth.User`, null=True, blank=True, on_delete=SET_NULL, related_name='+')
* `delete_reason` (CharField(max_length=255), null=True, blank=True)

**Managers:**
* `objects`: Trả về `QuerySet` lọc `is_deleted=False`.
* `all_objects`: Trả về toàn bộ bản ghi (kể cả bản ghi trong Thùng rác).

---

### 4.2. Danh sách 15 Thực thể Chi tiết

#### Ứng dụng `organization`
1. **`Department`** (Phòng ban)
   * `name_en` (CharField(100), unique active)
   * `name_ja` (CharField(100), null=True, blank=True)
2. **`Person`** (Nhân viên)
   * `staff_code` (CharField(50)) -> Partial unique constraint `(staff_code, is_deleted=False)`
   * `full_name` (CharField(100))
   * `department` (ForeignKey to `Department`, null=True, blank=True, on_delete=SET_NULL)
   * `status` (CharField(20), choices=[('active', 'Active / Đang làm việc'), ('resigned', 'Resigned / Đã nghỉ việc')], default='active')

#### Ứng dụng `assets`
3. **`AssetCategory`** (Loại thiết bị: Laptop, Monitor, Phone, Mouse...)
   * `name` (CharField(50), unique active)
4. **`Asset`** (Thiết bị IT cụ thể)
   * `asset_code` (CharField(50)) -> Partial unique constraint `(asset_code, is_deleted=False)`
   * `category` (ForeignKey to `AssetCategory`, on_delete=PROTECT)
   * `contract_line` (ForeignKey to `contracts.ContractLine`, null=True, blank=True, on_delete=SET_NULL)
   * `model` (CharField(150), null=True, blank=True)
   * `serial` (CharField(100), null=True, blank=True) -> Partial unique constraint `(serial, is_deleted=False)`
   * `hwid` (CharField(100), null=True, blank=True)
   * `mac_address` (CharField(50), null=True, blank=True)
   * `status` (CharField(20), choices=[('in_stock', 'Trong kho'), ('loaned', 'Đang mượn'), ('lost', 'Mất')], default='in_stock')
   * `note` (TextField, null=True, blank=True)
5. **`Assignment`** (Lịch sử mượn-trả thiết bị)
   * `asset` (ForeignKey to `Asset`, on_delete=PROTECT)
   * `person` (ForeignKey to `Person`, on_delete=PROTECT)
   * `borrowed_at` (DateField)
   * `returned_at` (DateField, null=True, blank=True)
   * `note` (TextField, null=True, blank=True)

#### Ứng dụng `licenses`
6. **`LicenseProduct`** (Danh mục phần mềm bản quyền)
   * `name` (CharField(100), unique active) - Ví dụ: IJCAD, Trend Micro, Office LTSC...
7. **`License`** (Gói bản quyền đã mua)
   * `product` (ForeignKey to `LicenseProduct`, on_delete=PROTECT)
   * `seats` (PositiveIntegerField, default=1)
   * `license_key` (CharField(255), null=True, blank=True)
   * `start_date` (DateField, null=True, blank=True)
   * `expiry_date` (DateField, null=True, blank=True) - Trống nghĩa là Vĩnh viễn (Perpetual)
8. **`LicenseAssignment`** (Gán license cho máy hoặc người)
   * `license` (ForeignKey to `License`, on_delete=PROTECT)
   * `asset` (ForeignKey to `Asset`, null=True, blank=True, on_delete=PROTECT)
   * `person` (ForeignKey to `Person`, null=True, blank=True, on_delete=PROTECT)
   * `assigned_at` (DateField)
   * `removed_at` (DateField, null=True, blank=True)

#### Ứng dụng `cards`
9. **`Room`** (Phòng cần kiểm soát thẻ: Kho, Server Room, Document Room...)
   * `name` (CharField(100), unique active)
10. **`AccessCard`** (Thẻ từ vật lý)
    * `card_no` (CharField(50)) -> Partial unique constraint `(card_no, is_deleted=False)`
11. **`AccessCardRoom`** (Bảng nối quyền ra vào phòng)
    * `card` (ForeignKey to `AccessCard`, on_delete=CASCADE)
    * `room` (ForeignKey to `Room`, on_delete=CASCADE)
    * Unique constraint `(card, room, is_deleted=False)`
12. **`CardLoan`** (Lịch sử mượn thẻ)
    * `card` (ForeignKey to `AccessCard`, on_delete=PROTECT)
    * `person` (ForeignKey to `Person`, null=True, blank=True, on_delete=PROTECT)
    * `external_name` (CharField(100), null=True, blank=True)
    * `external_company` (CharField(100), null=True, blank=True)
    * `purpose` (CharField(255), null=True, blank=True)
    * `borrowed_at` (DateField)
    * `returned_at` (DateField, null=True, blank=True)

#### Ứng dụng `contracts`
13. **`Contract`** (Hợp đồng mua sắm)
    * `code` (CharField(50)) -> Partial unique constraint `(code, is_deleted=False)` (ví dụ: KHCM-2408-0113)
    * `delivery_status` (CharField(20), choices=[('pending', 'Chưa giao'), ('delivered', 'Đã giao')], default='pending')
14. **`ContractLine`** (Chi tiết từng dòng hàng hợp đồng)
    * `contract` (ForeignKey to `Contract`, on_delete=CASCADE, related_name='lines')
    * `item_type` (CharField(100))
    * `spec` (TextField, null=True, blank=True)
    * `qty_ordered` (PositiveIntegerField)
    * *`qty_received`: Thuộc tính tính toán động (Computed property) từ số lượng `Asset` liên kết.*

#### Nhật ký Thay đổi (Audit Trail)
15. **`AuditLog`** (Lưu vết thay đổi bất biến qua `django-auditlog` hoặc custom model)
    * `user` (ForeignKey to `auth.User`, null=True, on_delete=SET_NULL)
    * `created_at` (DateTimeField, auto_now_add=True)
    * `table_name` (CharField(100))
    * `record_id` (PositiveIntegerField)
    * `action` (CharField(20), choices=[('create', 'Thêm'), ('update', 'Sửa'), ('delete', 'Xóa mềm'), ('restore', 'Khôi phục')])
    * `before_after` (JSONField, null=True, blank=True)

---

## 5. Phân quyền RBAC, Bảo mật & Đa ngôn ngữ (RBAC & Security)

### 5.1. Ma trận 3 Nhóm quyền (Groups & Permissions)

* **Admin (IT):** Toàn quyền (Đọc, Ghi, Sửa, Xóa mềm, Khôi phục từ Thùng rác, Quản lý tài khoản người dùng & Nhóm quyền).
* **GA Manager:**
  * Nhân sự (`Person`, `Department`): Đọc, Thêm, Sửa.
  * Thẻ ra vào (`AccessCard`, `Room`, `CardLoan`): Đọc, Thêm, Sửa, Xóa.
  * Tài sản, Hợp đồng: Chỉ Đọc.
  * License, Audit Log, Thùng rác: Không được phép truy cập.
* **Executive (Giám đốc):**
  * Chỉ Đọc (View-only) trên toàn bộ hệ thống (Nhân sự, Tài sản, License, Thẻ, Hợp đồng, Audit Log).
  * License Key hiển thị ở chế độ che mờ.
  * Không có quyền thêm/sửa/xóa hay truy cập Thùng rác.

### 5.2. Che mờ Dữ liệu Nhạy cảm (Data Masking)
* Phương thức hiển thị `license_key`:
  * Nếu `request.user.is_superuser` hoặc user thuộc nhóm `IT Admin`: Hiển thị rõ chuỗi key.
  * Người dùng khác: Hiển thị chuỗi mặt nạ `••••••••••••`.
* Hệ thống tuyệt đối không cung cấp trường lưu trữ mật khẩu người dùng máy tính hay email.

### 5.3. Phiên làm việc & Bảo vệ
* `SESSION_COOKIE_AGE = 1800` (Tự động đăng xuất sau 30 phút không thao tác).
* `SESSION_SAVE_EVERY_REQUEST = True`.
* Bật CSRF protection, Clickjacking protection (`X_FRAME_OPTIONS = 'DENY'`).

### 5.4. Đa ngôn ngữ (i18n) & Theme
* Bật `USE_I18N = True`. Ngôn ngữ hỗ trợ: `en` (English), `ja` (日本語).
* Đặt widget chuyển ngôn ngữ trực quan tại Header của Admin. Lựa chọn ngôn ngữ được lưu trong Session.
* Hỗ trợ Dark/Light mode tự động dựa trên cài đặt giao diện của hệ điều hành.

---

## 6. Các Màn hình & Luồng Nghiệp vụ Mở rộng (Extended Features)

### 6.1. Trang Tổng quan (Dashboard FR-13)
Nhúng trực tiếp vào trang chủ Admin (`/admin/`):
1. **Thẻ đếm Tài sản:**
   * Tổng số tài sản đang quản lý.
   * Số lượng *Trong kho* (In Stock).
   * Số lượng *Đang mượn* (Loaned).
   * Số lượng *Mất* (Lost).
2. **Cảnh báo License (Hạn 60 ngày):**
   * Danh sách các license có `expiry_date <= today + 60 days` hoặc đã quá hạn.
   * Hiển thị: Tên phần mềm, số seats, ngày hết hạn, số ngày còn lại (highlight màu vàng/đỏ).
3. **Thẻ đang cho mượn:**
   * Danh sách thẻ chưa trả (`returned_at IS NULL`).
   * Hiển thị: Số thẻ, người mượn (Nhân viên / Khách ngoài), Công ty, Phòng được vào, Ngày mượn.

### 6.2. Tra cứu Toàn cục (Global Search FR-03)
* Ô tìm kiếm đặt trên header điều hướng.
* Quét đồng thời qua:
  * `Asset`: `asset_code`, `serial`, `hwid`, `mac_address`, `model`.
  * `Person`: `full_name`, `staff_code`.
  * `Contract`: `code`.
  * `AccessCard`: `card_no`.
* Trả về kết quả phân nhóm kèm link chi tiết bản ghi.

### 6.3. Hồ sơ Tổng hợp 1 Người (Person 360 Profile FR-08)
Tại trang chi tiết nhân viên, có link dẫn tới trang hồ sơ tổng hợp:
* **Thiết bị đang giữ:** Danh sách thiết bị có `Assignment.returned_at IS NULL`.
* **Lịch sử thiết bị:** Lịch sử tất cả các máy nhân viên này từng mượn và ngày trả.
* **License đang gán:** Các license gán trực tiếp cho nhân viên hoặc gán vào máy mà nhân viên đang giữ.
* **Thẻ ra vào:** Thẻ đang mượn và lịch sử mượn thẻ.

### 6.4. Quản lý Hợp đồng & Tự động Đếm (FR-11)
* Trong `ContractLineAdmin`, cột `qty_received` được tính toán tự động bằng:
  `Asset.objects.filter(contract_line=line).count()`.
* Hiển thị chỉ báo hoàn thành: `qty_received / qty_ordered` (Đã nhận đủ / Chưa nhận đủ).

### 6.5. Thùng rác & Khôi phục (Trash Management)
* Menu "Thùng rác" chỉ hiển thị với IT Admin.
* Danh sách hiển thị các bản ghi có `is_deleted=True` kèm lý do xóa (`delete_reason`), người xóa, ngày xóa.
* Action "Khôi phục": Đặt lại `is_deleted=False`, `delete_reason=None`, và ghi 1 log `Restore` vào Audit Log.

---

## 7. Ràng buộc Dữ liệu & Xử lý Ngoại lệ (Validations)

1. **Chặn xóa tài sản đang sử dụng:** Không cho phép xóa `Asset` nếu `status == 'loaned'` hoặc tồn tại `Assignment` có `returned_at IS NULL`.
2. **Chặn xóa License đang gán:** Không cho phép xóa `License` nếu còn `LicenseAssignment` có `removed_at IS NULL`.
3. **Chặn xóa Thẻ đang mượn:** Không cho phép xóa `AccessCard` nếu còn `CardLoan` có `returned_at IS NULL`.
4. **Validation ngày tháng:** `returned_at` không được trước `borrowed_at` trong `Assignment` và `CardLoan`.
5. **Gán License:** `LicenseAssignment` bắt buộc phải có ít nhất `asset` hoặc `person`.
6. **Mượn thẻ người ngoài:** Nếu `person` để trống trong `CardLoan`, bắt buộc phải nhập `external_name`.
7. **Lý do xóa mềm:** Bắt buộc nhập `delete_reason` khi thực hiện thao tác xóa mềm trên giao diện Admin.

---

## 8. Khởi tạo & Kiểm thử Tự động (Testing & Bootstrap)

### 8.1. Lệnh Khởi tạo Hệ thống (`init_system`)
Lệnh `python manage.py init_system` thực hiện:
1. Tạo 3 Group: `IT Admin`, `GA Manager`, `Executive`.
2. Gán chính xác các quyền theo bảng ma trận RBAC.
3. Tạo tài khoản Superuser mặc định cho IT (`admin / tokuadmin2026`).
4. Nạp dữ liệu danh mục ban đầu:
   * Phòng ban TVC (General Affairs, IT, Sales, Production, Finance, Management).
   * Loại tài sản (Laptop, Monitor, Desktop, Smartphone, Mouse, Adapter, Headset).
   * Danh mục phần mềm (IJCAD, Office LTSC, Adobe Acrobat PDF, Trend Micro Apex One, Microsoft 365, Visio, Windows Pro).
   * Danh sách phòng (Kho, Server Room, Document Room, Production Area).

### 8.2. Chiến lược Kiểm thử Tự động
Tạo bộ kiểm thử toàn diện với Django Test Runner / Pytest:
* `test_models.py`: Kiểm thử ràng buộc toàn vẹn, partial unique constraints, computed fields.
* `test_soft_delete.py`: Kiểm thử việc ẩn bản ghi xóa mềm, chặn xóa tài sản đang mượn, khôi phục từ thùng rác.
* `test_rbac.py`: Kiểm thử quyền hạn 3 nhóm đối với từng module, kiểm tra che mờ `license_key`.
* `test_features.py`: Kiểm thử logic Dashboard (cảnh báo 60 ngày), tìm kiếm toàn cục, hồ sơ nhân sự 360.
