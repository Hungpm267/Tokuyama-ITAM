# Hệ thống Quản lý Tài sản IT (ITAM) – Tokuyama Vietnam (FastAPI Edition)

Hệ thống quản lý tập trung toàn bộ tài sản thiết bị IT, bản quyền phần mềm (license), thẻ từ ra vào văn phòng và hợp đồng mua sắm cho **Tokuyama Vietnam**.
Ứng dụng được xây dựng trên nền tảng **FastAPI**, **SQLAlchemy 2.0**, **SQLAdmin** và giao diện **Swiss Anchor Design System** (tối giản, tinh tế, 1px border hairline, màu xanh Yves Klein `#002FA7`, không emoji cồng kềnh, tối ưu bảng biểu và số liệu).

---

## 1. Điểm nổi bật & Tính năng cốt lõi

* **Kiến trúc Hiện đại & Hiệu năng cao:**
  * **Backend:** FastAPI (Python 3.12 - 3.14), async/await, Pydantic v2 validation.
  * **ORM & Database:** SQLAlchemy 2.0 hỗ trợ cả SQLite (mặc định) và PostgreSQL qua chuỗi kết nối `DATABASE_URL`.
  * **Quản trị CRUD:** Tích hợp **SQLAdmin** tại `/admin` có xác thực session bảo mật.
  * **Giao diện người dùng:** Jinja2 templates chuẩn thiết kế Thụy Sĩ (**Swiss Anchor**).
  * **Tài liệu API tự động:** Interactive OpenAPI / Swagger UI tại `/docs` và ReDoc tại `/redoc`.

* **Đáp ứng đầy đủ 13 Yêu cầu Nghiệp vụ (BRD):**
  1. **Nhân sự (`Person`, `Department`):** Quản lý mã nhân viên (`staff_code`), tên tiếng Anh / tiếng Nhật, trạng thái làm việc/nghỉ việc.
  2. **Tài sản IT (`Asset`):** Mã tài sản, model, serial, HWID, MAC address. Trạng thái tự động: *Trong kho (in_stock)*, *Đang mượn (loaned)*, *Mất (lost)*.
  3. **Mượn - Trả Thiết bị (`Assignment`):** Lưu 100% lịch sử các lần mượn - trả của nhân viên.
  4. **Bản quyền License (`License`, `LicenseAssignment`):** Gói phần mềm, số seats, gán theo máy hoặc người, cảnh báo hạn dùng trong 60 ngày hoặc vĩnh viễn, che mờ license key theo quyền.
  5. **Thẻ từ ra vào (`AccessCard`, `CardLoan`):** Quản lý thẻ từ, phân quyền theo phòng, cho mượn thẻ nội bộ hoặc nhà thầu bên ngoài (External Vendor).
  6. **Hợp đồng mua sắm (`Contract`, `ContractLine`):** Quản lý mã hợp đồng (KHCM-...), tự động tính số lượng thực nhận từ thiết bị gắn vào dòng hàng.
  7. **Cơ chế Xóa mềm (Soft Delete):** Mọi bảng kế thừa 8 trường kiểm toán (`created_at`, `created_by_id`, `updated_at`, `updated_by_id`, `is_deleted`, `deleted_at`, `deleted_by_id`, `delete_reason`).
  8. **Thùng Rác & Khôi Phục (Trash & Restore):** Chỉ IT Admin mới có quyền truy cập `/trash` và khôi phục bản ghi đã xóa.
  9. **Truy vết Bất biến (Audit Log):** Lưu trữ hành động (create, update, delete, restore) kèm diff dữ liệu dạng JSON.
  10. **Phân quyền 3 Nhóm RBAC:**
      * **IT Admin:** Toàn quyền hệ thống, quản lý tài khoản, thùng rác.
      * **GA Manager:** Quản lý nhân sự, toàn quyền quản lý thẻ từ, xem tài sản.
      * **Executive (Giám đốc):** Xem báo cáo và toàn bộ dữ liệu, che mờ license key.
  11. **Dashboard Tổng quan (FR-13):** Thống kê số lượng thiết bị theo trạng thái, cảnh báo license sắp hết hạn trong 60 ngày, danh sách thẻ đang cho mượn chưa trả.
  12. **Tìm kiếm Toàn cục (Global Search FR-03):** Tra cứu tức thì theo mã tài sản, serial, HWID, MAC, tên nhân viên, mã hợp đồng.
  13. **Hồ sơ Nhân sự 360 (Person Profile FR-08):** Xem toàn bộ thiết bị đang giữ, lịch sử máy đã trả, license phần mềm và thẻ từ đang mượn của một nhân viên.

---

## 2. Hướng dẫn Khởi Chạy Nhanh (Quickstart)

### 2.1. Yêu cầu môi trường
* Python 3.10+ (đã kiểm thử hoàn hảo trên Python 3.14).
* SQLite (có sẵn) hoặc PostgreSQL 14+.

### 2.2. Kích hoạt môi trường và cài đặt thư viện
Mở PowerShell tại thư mục dự án `toku-app`:

```powershell
# Kích hoạt môi trường ảo
.\venv\Scripts\Activate.ps1

# Cài đặt thư viện (nếu cài mới trên máy khác)
pip install -r requirements.txt
```

### 2.3. Khởi chạy ứng dụng (1 lệnh duy nhất)
Chỉ cần chạy lệnh sau, hệ thống sẽ **tự động khởi tạo database, chạy seed dữ liệu mẫu và tài khoản ban đầu**:

```powershell
python run.py
```
*(Hoặc chạy qua uvicorn trực tiếp: `uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload`)*

---

## 3. Các địa chỉ truy cập & Tài khoản mặc định

| Mục | Địa chỉ URL | Mô tả |
| :--- | :--- | :--- |
| **Cổng Web Portal** | `http://127.0.0.1:8000/` | Giao diện Swiss Anchor với Dashboard, Tìm kiếm, Hồ sơ nhân viên, Thùng rác |
| **Đăng nhập Web** | `http://127.0.0.1:8000/login` | Form đăng nhập chuẩn thiết kế tối giản Thụy Sĩ |
| **Bảng Quản trị CRUD** | `http://127.0.0.1:8000/admin` | SQLAdmin mạnh mẽ cho phép quản lý chi tiết mọi bảng dữ liệu |
| **Interactive API Docs** | `http://127.0.0.1:8000/docs` | Swagger UI tương tác trực tiếp với REST API |
| **Alternative API Docs**| `http://127.0.0.1:8000/redoc`| ReDoc tài liệu API |

### Tài khoản đăng nhập hệ thống:

| Tên đăng nhập | Mật khẩu | Phân quyền (RBAC) | Quyền hạn chính |
| :--- | :--- | :--- | :--- |
| **`admin`** | `tokuadmin2026` | **IT Admin** | Toàn quyền hệ thống, xem/khôi phục Thùng Rác, quản trị SQLAdmin |
| **`ga_manager`** | `toku2026ga` | **GA Manager** | Quản lý thẻ từ ra vào, nhân sự, phòng ban, mượn trả thẻ |
| **`director`** | `toku2026exec` | **Executive** | Giám đốc xem báo cáo, thống kê, che mờ license key nhạy cảm |

---

## 4. Chạy Kiểm Thử Tự Động (Test Suite)

Hệ thống có bộ unit test và integration test hoàn chỉnh bằng `pytest` + `httpx.AsyncClient`:

```powershell
.\venv\Scripts\pytest -v
```

Kết quả: **9/9 tests passed (100%)** bao gồm xác thực, phân quyền, API CRUD, Dashboard, Web Search, Trash/Restore và Soft Delete.

---

## 5. Cấu hình Cơ sở Dữ liệu PostgreSQL (Tùy chọn)

Nếu muốn chuyển từ SQLite sang PostgreSQL trên máy chủ hoặc cloud:
1. Mở tệp `.env` và sửa dòng `DATABASE_URL`:
   ```env
   # PostgreSQL Local:
   DATABASE_URL=postgresql://postgres:mat_khau@localhost:5432/toku_itam

   # Hoặc PostgreSQL Cloud (Neon / Supabase):
   DATABASE_URL=postgresql://user:password@ep-server.neon.tech/toku_itam?sslmode=require
   ```
2. Chạy `python run.py`. Hệ thống tự động tạo toàn bộ bảng và nạp dữ liệu mẫu trên PostgreSQL.
