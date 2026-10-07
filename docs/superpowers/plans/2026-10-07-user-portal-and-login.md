# Kế hoạch Thực hiện: Cổng Web Portal & Màn hình Đăng nhập (User Portal & Login Flow)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Xây dựng màn hình đăng nhập công khai `/login` và Cổng Web Portal (`/`) cho mọi vai trò (Admin, GA Manager, Executive), tự động phân luồng điều hướng, bảo vệ CSRF và hiển thị Dashboard tổng quan tài sản theo Swiss Style.

**Architecture:** Sử dụng FastAPI + Jinja2 server-rendered templates kế thừa layout chung (`base.html`), định tuyến qua router mới `app/routers/portal.py`, tích hợp xác thực Argon2id và audit log từ `app/core/`, phân luồng chuyển hướng thông minh dựa trên `User.role.code`.

**Tech Stack:** Python 3.12, FastAPI, Jinja2, SQLAlchemy 2.x, PostgreSQL, Argon2id (`app/core/security.py`), Swiss Theme CSS.

**Spec:** `docs/superpowers/specs/2026-10-07-user-portal-and-login-design.md`

## Global Constraints

- Schema đóng băng theo `GEMINI.md`: không sửa `app/models.py`.
- Form POST bắt buộc có `csrf_token` và kiểm tra hợp lệ.
- Jinja2 autoescape luôn bật, tuyệt đối không dùng `|safe` với dữ liệu người dùng.
- Mật khẩu đăng nhập chỉ xử lý qua `verify_password` (Argon2id), không lưu mật khẩu thô.
- Ghi audit log `LOGIN` và `LOGIN_FAIL` cho mọi lượt đăng nhập.
- `ruff check .` và toàn bộ test suite `pytest` phải xanh 100%.

---

### Task 1: Khởi tạo Khung Giao diện Chung (Portal Base Template)

**Files:**
- Create: `templates/portal/base.html`
- Test: `tests/test_portal.py`

**Interfaces:**
- Produces: `templates/portal/base.html` với sticky topbar, logo Tokuyama, menu phân quyền (Dashboard, Assets, Assignments, Phones, Admin link), bộ chuyển ngôn ngữ (VI/EN/JA), badge người dùng và nút Đăng xuất.

- [ ] **Step 1: Viết test kiểm tra template base có thể nạp được**
- [ ] **Step 2: Tạo file `templates/portal/base.html` với cấu trúc chuẩn Swiss Design, header dính (sticky top-0 z-50), không viền màu AI**
- [ ] **Step 3: Chạy test kiểm tra template render thành công**
- [ ] **Step 4: Commit thay đổi**

---

### Task 2: Xây dựng Giao diện Đăng nhập (Login Template)

**Files:**
- Create: `templates/portal/login.html`
- Test: `tests/test_portal.py`

**Interfaces:**
- Consumes: `csrf_token`, `error` (nếu có), `username` (nếu có)
- Produces: `templates/portal/login.html` với thẻ card trung tâm, logo Tokuyama, trường `username`, `password`, `<input type="hidden" name="csrf_token">`, nút đăng nhập đỏ `#C51118`.

- [ ] **Step 1: Tạo file `templates/portal/login.html` kế thừa hoặc độc lập trang nhã**
- [ ] **Step 2: Kiểm tra cấu trúc form POST `/login`, trường CSRF và hiển thị thông báo lỗi**
- [ ] **Step 3: Commit thay đổi**

---

### Task 3: Xây dựng Giao diện Trang Tổng quan (Dashboard Template)

**Files:**
- Create: `templates/portal/dashboard.html`
- Test: `tests/test_portal.py`

**Interfaces:**
- Consumes: Kế thừa `portal/base.html`, nhận các biến KPI: `total_assets`, `in_stock_assets`, `in_use_assets`, `repair_assets`, `expiring_licenses`, `active_card_loans`, `user`
- Produces: Giao diện thẻ KPI hiện đại, bảng license sắp hết hạn (60 ngày), bảng thẻ đang mượn.

- [ ] **Step 1: Tạo file `templates/portal/dashboard.html` kế thừa `portal/base.html`**
- [ ] **Step 2: Thêm các thẻ KPI hiện đại không viền màu sặc sỡ, bố cục Swiss gọn gàng**
- [ ] **Step 3: Commit thay đổi**

---

### Task 4: Triển khai Portal Router (`app/routers/portal.py`)

**Files:**
- Create: `app/routers/portal.py`
- Test: `tests/test_portal.py`

**Interfaces:**
- Consumes: `app/core/security.py`, `app/core/audit.py`, `app/models.py`, `app/db.py`
- Produces:
  - `GET /login`: Render login page hoặc redirect nếu đã login
  - `POST /login`: Xử lý đăng nhập, check CSRF, audit log, redirect `/admin` nếu ADMIN hoặc `/` nếu EXECUTIVE/GA
  - `GET /`: Dashboard KPI query, redirect `/login` nếu chưa đăng nhập, redirect `/admin` nếu ADMIN
  - `GET /logout`: Clear session & redirect `/login`

- [ ] **Step 1: Viết failing test trong `tests/test_portal.py` cho các route `/login`, `/logout`, `/`**
- [ ] **Step 2: Chạy test để xác nhận test thất bại (do chưa có router)**
- [ ] **Step 3: Viết code `app/routers/portal.py` với đầy đủ logic CSRF, Argon2id, audit log, KPI DB query**
- [ ] **Step 4: Chạy test để xác nhận test bước này vượt qua**
- [ ] **Step 5: Commit thay đổi**

---

### Task 5: Gắn kết Router vào `app/main.py` và Cập nhật Điều hướng

**Files:**
- Modify: `app/main.py`
- Test: `tests/test_portal.py`

**Interfaces:**
- Gắn `app.include_router(portal_router)`
- Xóa `@app.get("/") -> RedirectResponse("/admin")` cũ

- [ ] **Step 1: Chỉnh sửa `app/main.py`**
- [ ] **Step 2: Chạy kiểm thử tích hợp**
- [ ] **Step 3: Commit thay đổi**

---

### Task 6: Kiểm thử Toàn diện & Xác thực Hợp đồng (Regression & Lint)

**Files:**
- Test: `tests/test_portal.py`, `tests/test_phase1.py`, `tests/test_constraints.py`

- [ ] **Step 1: Chạy toàn bộ test suite `pytest` (đảm bảo cả 65 test cũ và test mới đều PASS)**
- [ ] **Step 2: Chạy `ruff check .` bảo đảm code sạch hoàn toàn**
- [ ] **Step 3: Kiểm tra trực tiếp trên trình duyệt hoặc qua client HTTP**
- [ ] **Step 4: Commit hoàn tất Phase 2 Portal Foundation**
