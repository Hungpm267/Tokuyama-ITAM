# Thiết kế Kỹ thuật: Cổng Web Portal & Màn hình Đăng nhập Người dùng (User Portal & Login Flow)

- **Ngày ban hành:** 2026-10-07
- **Tác giả:** Antigravity (AI Assistant) & IT Admin Tokuyama Vietnam
- **Trạng thái:** Đã phê duyệt (Approved)
- **Tài liệu liên quan:** `docs/BRD.md`, `GEMINI.md`

---

## 1. Mục tiêu & Bối cảnh

### 1.1 Bối cảnh
Trước đây, hệ thống ITAM Tokuyama Vietnam chỉ có cổng kỹ thuật `/admin` (SQLAdmin) dành riêng cho vai trò `ADMIN`. Khi người dùng có vai trò khác như `EXECUTIVE` (Ban giám đốc, ví dụ tài khoản `ninh`) hay `GA_MANAGER` (Trưởng phòng GA) đăng nhập vào `/admin`, họ bị từ chối truy cập. Đồng thời, đường dẫn gốc `/` đang chuyển hướng cứng về `/admin`, và chưa có trang giao diện người dùng chung `/login`.

### 1.2 Mục tiêu
1. Xây dựng Cổng ứng dụng web chính (Web Portal) sử dụng giao diện render server (Jinja2).
2. Xây dựng màn hình đăng nhập công khai `/login` cho mọi vai trò (Admin, GA Manager, Executive).
3. Triển khai cơ chế điều hướng thông minh sau đăng nhập:
   - Vai trò `ADMIN` $\rightarrow$ Tự động chuyển hướng vào `/admin` (Cổng quản trị kỹ thuật).
   - Vai trò `EXECUTIVE` & `GA_MANAGER` $\rightarrow$ Tự động chuyển hướng vào `/` (Dashboard Tổng quan).
4. Xây dựng trang Tổng quan (`/`) với các chỉ số KPI tài sản (FR-17) theo phong cách Swiss Design tối giản, chuẩn nhận diện thương hiệu Tokuyama Vietnam.
5. Đảm bảo toàn vẹn các bất biến bảo mật: CSRF token cho form POST, phiên làm việc 30 phút, ghi nhật ký audit log (`LOGIN`, `LOGIN_FAIL`), autoescape chống XSS.

---

## 2. Kiến trúc Hệ thống & Luồng Dữ liệu

### 2.1 Router `app/routers/portal.py`
Router mới này quản lý toàn bộ các trang giao diện HTML cho người dùng:

- `GET /login`:
  - Kiểm tra phiên làm việc hiện tại (`request.cookies.get("itam_session")` hoặc `request.session`).
  - Nếu đã đăng nhập:
    - Nếu là `ADMIN`: chuyển hướng về `/admin`.
    - Nếu là vai trò khác: chuyển hướng về `/`.
  - Nếu chưa đăng nhập: Sinh ra một `csrf_token` lưu trong session, render template `portal/login.html`.
- `POST /login`:
  - Nhận form data: `username`, `password`, `csrf_token`.
  - Xác thực `csrf_token` trùng khớp với token trong session (chặn tấn công CSRF).
  - Tìm kiếm người dùng còn hoạt động (`is_active=True`, `is_deleted=False`).
  - Kiểm tra mật khẩu bằng hàm `verify_password(password, user.password_hash)` (thuật toán Argon2id).
  - Nếu thất bại:
    - Ghi nhận `AuditAction.LOGIN_FAIL` vào bảng `audit_logs`.
    - Render lại `portal/login.html` với thông báo lỗi: "Tên đăng nhập hoặc mật khẩu không chính xác."
  - Nếu thành công:
    - Cập nhật `user.last_login_at = now()`.
    - Ghi nhận `AuditAction.LOGIN` vào bảng `audit_logs`.
    - Tạo session token (JWT) và gán cookie `itam_session` với `httponly=True`, `samesite="lax"`, `max_age=1800` (30 phút).
    - Cập nhật `request.session["user_id"] = user.id`.
    - Điều hướng theo vai trò:
      - `ADMIN` $\rightarrow$ `RedirectResponse(url="/admin", status_code=303)`
      - `EXECUTIVE` hoặc `GA_MANAGER` $\rightarrow$ `RedirectResponse(url="/", status_code=303)`
- `GET /`:
  - Yêu cầu xác thực người dùng qua dependency `get_current_user_optional` hoặc kiểm tra session.
  - Nếu chưa đăng nhập: `RedirectResponse(url="/login", status_code=303)`.
  - Nếu là `ADMIN`: chuyển hướng về `/admin`.
  - Nếu là `EXECUTIVE` hoặc `GA_MANAGER`:
    - Truy vấn tổng hợp số liệu KPI từ cơ sở dữ liệu:
      - Tổng số thiết bị (`Asset` có `is_deleted=False`).
      - Số thiết bị theo trạng thái: Trong kho (`IN_STOCK`), Đang sử dụng (`IN_USE`), Đang sửa chữa (`UNDER_REPAIR`).
      - Danh sách license phần mềm sắp hết hạn trong vòng 60 ngày tới (FR-17).
      - Danh sách thẻ ra vào đang cho mượn và thẻ quá hạn hẹn trả.
    - Render template `portal/dashboard.html`.
- `GET /logout`:
  - Xoá cookie `itam_session`.
  - Xoá dữ liệu phiên trong `request.session`.
  - Chuyển hướng về `/login`.

### 2.2 Tích hợp vào `app/main.py`
- Gắn kết `portal.router` vào ứng dụng FastAPI: `app.include_router(portal_router)`.
- Gỡ bỏ chuyển hướng cứng `@app.get("/") -> RedirectResponse("/admin")` để route `/` thuộc quyền quản lý của Web Portal.

---

## 3. Thiết kế Giao diện Người dùng (Templates & UI)

### 3.1 Cấu trúc Thư mục Templates
```
templates/
  portal/
    base.html          # Khung sườn chung (Header cố định, Menu, Đổi ngôn ngữ, Thông tin user)
    login.html         # Form đăng nhập công khai
    dashboard.html     # Trang tổng quan KPI cho Executive & GA Manager
```

### 3.2 Quy chuẩn Thiết kế (Swiss Theme & Tokuyama Palette)
- **Topbar cố định (`sticky top-0 z-50`)**:
  - Không bị cuộn mất khi người dùng cuộn trang xem dữ liệu dài.
  - Thanh bar màu trắng tinh (`#FFFFFF`), viền dưới mảnh (`#E2E8F0`).
  - Logo chính thức Tokuyama Vietnam (`/static/img/logo.svg`) ở góc trái.
  - Menu điều hướng động:
    - Trang chủ / Tổng quan (`/`)
    - Tài sản (`/assets` - chuẩn bị cho giai đoạn tiếp theo)
    - Mượn - Trả (`/assignments` - chuẩn bị cho giai đoạn tiếp theo)
    - Danh bạ thoại (`/phones` - Phone List)
    - Nút quản trị kỹ thuật (`/admin` - chỉ hiển thị nếu tài khoản là Admin).
  - Bộ điều khiển góc phải:
    - Chuyển đổi ngôn ngữ: `VI | EN | JA` (gọi endpoint `/set-lang?lang=...`).
    - Huy hiệu người dùng: Tên hiển thị (`display_name`) + Vai trò (`Executive`, `GA Manager`).
    - Nút Đăng xuất (`/logout`).
- **Cards & Bố cục Nội dung**:
  - Font chữ sans-serif (Inter / System font) đồng nhất toàn ứng dụng.
  - Thẻ KPI nền trắng sạch sẽ, viền mảnh `#E2E8F0`, đổ bóng dịu `shadow-sm`, không dùng viền màu sắc lòe loẹt.
  - Màu nhấn chính: Đỏ Tokuyama (`#C51118`).
  - Nền trang web màu xám nhẹ trung tính (`#F8FAFC`).

---

## 4. Bảo mật & Tính toàn vẹn

1. **CSRF Protection**: Mọi form gửi dữ liệu đều bắt buộc có `csrf_token`. Kiểm tra trước khi thực hiện bất kỳ thao tác truy vấn nào.
2. **XSS Protection**: Jinja2 kích hoạt autoescape mặc định. Không dùng bộ lọc `|safe` cho bất kỳ nội dung nào do người dùng nhập.
3. **Quản lý Phiên (Session Timeout)**: Cookie `itam_session` hết hạn sau 30 phút không hoạt động (1800 giây).
4. **Không lộ thông tin nhạy cảm**: Lỗi đăng nhập hiển thị thông báo chung ("Tên đăng nhập hoặc mật khẩu không chính xác"), không tiết lộ tài khoản có tồn tại hay không.
5. **Audit Logging**: Mọi lần đăng nhập (thành công hoặc thất bại) đều ghi nhận vào bảng `audit_logs` đầy đủ thời gian và địa chỉ IP.

---

## 5. Kế hoạch Kiểm thử (Verification & Test Suite)

Tạo file kiểm thử tự động `tests/test_portal.py` bao gồm:
1. `test_login_page_renders`: Kiểm tra `GET /login` trả về HTTP 200, hiển thị đúng form đăng nhập và có thẻ CSRF token.
2. `test_login_csrf_validation`: Kiểm tra gửi POST form không có CSRF token hoặc sai token bị trả về HTTP 400.
3. `test_login_wrong_password`: Kiểm tra đăng nhập sai mật khẩu bị từ chối, audit log ghi nhận `LOGIN_FAIL`.
4. `test_login_admin_redirect`: Kiểm tra tài khoản `ADMIN` đăng nhập thành công được chuyển hướng sang `/admin`.
5. `test_login_executive_redirect`: Kiểm tra tài khoản `EXECUTIVE` (ví dụ `ninh`) đăng nhập thành công được chuyển hướng sang `/`.
6. `test_unauthenticated_dashboard_redirect`: Kiểm tra chưa đăng nhập truy cập `/` bị chuyển hướng về `/login`.
7. `test_executive_dashboard_access`: Kiểm tra tài khoản `EXECUTIVE` truy cập `/` xem được nội dung Dashboard và các thẻ KPI.
8. `test_portal_logout`: Kiểm tra `GET /logout` xóa cookie và đưa về `/login`.
9. Kiểm tra toàn bộ 65 test trước đó của hệ thống bảo đảm tiếp tục xanh 100%.
10. Kiểm tra `ruff check .` không có bất kỳ lỗi linter nào.
