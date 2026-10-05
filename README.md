# Hệ thống Quản lý Tài sản IT (ITAM) – Tokuyama Vietnam (TVC)

Hệ thống quản lý tập trung toàn bộ tài sản thiết bị IT, bản quyền phần mềm (license), thẻ từ ra vào văn phòng và hợp đồng mua sắm theo mã hợp đồng cho Tokuyama Vietnam. Ứng dụng thay thế hoàn toàn các file và sheet Excel phân mảnh, đảm bảo một nguồn dữ liệu duy nhất (Single Source of Truth).

---

## 1. Tính năng cốt lõi (Core Features)

* **6 Module Nghiệp vụ Chuẩn Hóa:**
  1. **Nhân sự (`organization`):** Quản lý Danh mục Phòng ban (Anh/Nhật), Nhân viên TVC (`staff_code`), trạng thái làm việc/nghỉ việc.
  2. **Tài sản IT (`assets`):** Danh mục thiết bị (Laptop, màn hình, chuột...), mã tài sản, model, serial, HWID, MAC. Trạng thái tự động: *Trong kho*, *Đang mượn*, *Mất*.
  3. **Mượn - Trả Thiết bị (`assets`):** Lưu trữ 100% lịch sử các lần mượn của từng nhân viên; tự động cập nhật trạng thái thiết bị.
  4. **Bản quyền License (`licenses`):** Quản lý gói license, số lượng seats, gán cho máy hoặc người, cảnh báo hạn dùng (hạn 60 ngày hoặc vĩnh viễn), che mờ license key đối với người dùng không phải IT Admin.
  5. **Thẻ từ ra vào (`cards`):** Thẻ từ, danh sách phòng được phép vào, mượn thẻ cho nhân viên hoặc nhà thầu bên ngoài (tên, công ty), theo dõi thẻ chưa trả.
  6. **Hợp đồng mua sắm (`contracts`):** Quản lý mã hợp đồng (KHCM-...), dòng hàng đặt mua, tự động tính số lượng thực nhận từ thiết bị gắn vào dòng hàng.
* **Cơ chế Xóa Mềm (Soft Delete):** Mọi bảng nghiệp vụ kế thừa 8 trường kiểm toán (`created_at`, `created_by`, `updated_at`, `updated_by`, `is_deleted`, `deleted_at`, `deleted_by`, `delete_reason`). Ẩn mặc định các bản ghi đã xóa mềm; partial unique index cho phép tạo lại serial trùng khi bản ghi cũ đã xóa.
* **Thùng Rác & Khôi Phục (Trash & Restore):** Chỉ IT Admin mới có quyền xem bản ghi đã xóa mềm và khôi phục lại dữ liệu.
* **Truy vết Bất Biến (Audit Trail):** Tự động ghi lại toàn bộ thay đổi dữ liệu (diff JSON), không một ai có quyền sửa hoặc xóa nhật ký audit log.
* **Phân quyền 3 Nhóm RBAC:**
  * **IT Admin:** Toàn quyền hệ thống, quản trị tài khoản, khôi phục thùng rác.
  * **GA Manager:** Quản lý nhân sự, toàn quyền quản lý thẻ ra vào, xem tài sản/hợp đồng.
  * **Executive (Giám đốc):** Xem toàn bộ thông tin hệ thống, license key được che mờ.
* **Trang Tổng Quan (Dashboard FR-13):** Thống kê số lượng thiết bị theo trạng thái, cảnh báo license sắp hết hạn trong 60 ngày, danh sách thẻ đang cho mượn chưa trả.
* **Tìm Kiếm Toàn Cục (Global Search FR-03):** Tra cứu tức thì theo mã tài sản, serial, HWID, MAC, tên nhân viên, mã hợp đồng.
* **Hồ Sơ Nhân Sự 360 (Person Profile FR-08):** Xem toàn bộ thiết bị đang giữ, lịch sử máy đã trả, license phần mềm và thẻ từ đang mượn của một nhân viên.
* **Đa ngôn ngữ & Giao diện:** Hỗ trợ song ngữ Tiếng Anh (English) và Tiếng Nhật (日本語) với nút chọn ngôn ngữ trực quan trên Header; tự động chuyển chế độ Sáng / Tối (Dark/Light mode).

---

## 2. Hướng dẫn Khởi Chạy Nhanh (Quickstart)

### 2.1. Yêu cầu môi trường
* Python 3.10 trở lên (khuyến nghị Python 3.12, 3.13 hoặc 3.14).
* PostgreSQL 14+ hoặc SQLite (chạy mặc định cho môi trường thử nghiệm).

### 2.2. Kích hoạt môi trường và cài đặt
Mở PowerShell tại thư mục dự án `toku-app`:

```powershell
# Kích hoạt môi trường ảo
.\venv\Scripts\Activate.ps1

# Cài đặt thư viện nếu chạy trên máy mới
pip install -r requirements.txt
```

### 2.3. Khởi tạo cơ sở dữ liệu và dữ liệu mẫu (1 bước duy nhất)
Chạy lệnh khởi tạo hệ thống để tạo bảng, phân quyền RBAC và nạp danh mục:

```powershell
python manage.py migrate
python manage.py init_system
```

**Tài khoản đăng nhập mặc định:**
* **URL Quản trị:** `http://127.0.0.1:8000/admin/`
* **Tài khoản:** `admin`
* **Mật khẩu:** `tokuadmin2026`

### 2.4. Chạy Web Server trong mạng LAN nội bộ
Để IT Admin, GA Manager và Giám đốc trong mạng nội bộ công ty có thể truy cập được:

```powershell
python manage.py runserver 0.0.0.0:8000
```
*(Người dùng cùng mạng LAN truy cập qua địa chỉ: `http://<IP_LAPTOP_IT>:8000/admin/`)*

---

## 3. Cấu hình Cơ sở Dữ liệu PostgreSQL

Để chuyển sang dùng PostgreSQL local hoặc PostgreSQL online (Supabase/Neon/Server công ty), cấu hình biến `DATABASE_URL` trong tệp `.env`:

```env
# Mẫu kết nối PostgreSQL:
DATABASE_URL=postgres://postgres:mat_khau@localhost:5432/toku_itam

# Hoặc PostgreSQL Cloud có SSL:
DATABASE_URL=postgres://user:pass@ep-server.neon.tech/toku_itam?sslmode=require
```

Sau khi sửa `.env`, chạy lệnh migrate:
```powershell
python manage.py migrate
python manage.py init_system
```

---

## 4. Hướng dẫn Sao lưu & Khôi phục (Backup & Restore)

### Sao lưu dữ liệu (Backup định kỳ):
```powershell
# Sao lưu dữ liệu ra file SQL
pg_dump -U postgres -h localhost -d toku_itam > backup_toku_itam_$(Get-Date -Format "yyyyMMdd").sql
```

### Phục hồi dữ liệu khi chuyển sang máy khác:
```powershell
# 1. Tạo database mới
createdb -U postgres toku_itam

# 2. Khôi phục từ file backup
psql -U postgres -d toku_itam -f backup_toku_itam_YYYYMMDD.sql
```

---

## 5. Chạy Kiểm Thử Tự Động (Automated Tests)

Chạy toàn bộ 19 kịch bản kiểm thử (Models, Soft Delete, RBAC, Masking, Audit Log, Dashboard, Search, Profile):

```powershell
.\venv\Scripts\pytest -v
```
