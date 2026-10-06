# GEMINI.md — Bất biến của dự án ITAM Tokuyama Vietnam

**Đọc hết file này trước khi viết dòng code đầu tiên của mỗi phiên làm việc.**

Dự án: web app nội bộ quản lý tài sản IT, thay thế một loạt file Excel.
Stack: FastAPI + SQLAlchemy 2.x + Alembic + PostgreSQL + Jinja2 + SQLAdmin.
Người dùng: 5 người (1 IT làm Admin, 1 trưởng GA, 3 giám đốc người Nhật).
Tài liệu nghiệp vụ đầy đủ: `docs/BRD.md`.

---

## 0. Ba điều quan trọng nhất

1. **Schema đã đóng băng.** `app/models.py` là nguồn sự thật duy nhất. Không tạo
   file model khác, không sửa bảng bằng SQL tay, không gọi `Base.metadata.create_all()`.
2. **`tests/test_constraints.py` là hợp đồng, không phải gợi ý.** Nếu một test đỏ,
   cái sai là code mới. Không bao giờ sửa hay xoá test để code chạy được.
3. **Mật khẩu nhân viên là phần nhạy cảm nhất của hệ thống.** Mục 5 dưới đây là
   tuyệt đối. Không "tạm thời" nới ra để debug.

---

## 1. Bất biến về dữ liệu

| # | Quy tắc | Vì sao |
| --- | --- | --- |
| 1 | Mọi thay đổi schema đi qua Alembic (`alembic revision --autogenerate`) | Có dữ liệu thật, không dựng lại DB được |
| 2 | Trạng thái dùng ENUM native PostgreSQL, không dùng VARCHAR | Excel cũ có "Delivered to Mr. Chuong" ở cột trạng thái |
| 3 | Ràng buộc duy nhất dùng partial unique index `WHERE is_deleted = false` | Xoá mềm rồi nhập lại cùng serial phải được phép |
| 4 | "Chỉ một bản ghi đang mở" dùng partial index `WHERE <cột đóng> IS NULL` | `UNIQUE(asset_id, returned_at)` KHÔNG chặn được vì `NULL != NULL` |
| 5 | Mọi truy vấn trên bảng nghiệp vụ mặc định lọc `is_deleted = false` | — |
| 6 | Xoá là xoá mềm, bắt buộc có `delete_reason` | Có CHECK ở DB, không chỉ ở code |
| 7 | `assignments`, `license_assignments`, `card_loans`, `audit_logs` KHÔNG xoá, chỉ đóng bằng ngày kết thúc | Lịch sử không được ghi đè |
| 8 | Không thêm `delivered_qty` / `remaining_qty` vào `contract_lines` | Số đã nhận ĐẾM từ `assets.contract_line_id`. Cột gõ tay là nguồn sai lệch của sheet "PC_Qty summary" |
| 9 | Thuộc tính mở rộng được thì KHÔNG bao giờ là cột | Nhãn máy → `asset_tags`. Phần mềm → `license_products`. Thêm cái mới = INSERT, không migration |
| 10 | Bảng danh mục luôn có `name_en` và `name_ja` | Giao diện song ngữ |
| 11 | Quyền ra vào của thẻ lưu bằng bảng nối `access_card_locations` | Không lưu câu mô tả kiểu "trừ Server Room" |
| 12 | `audit_logs` chỉ INSERT và SELECT, có trigger DB chặn | Người có chuỗi kết nối cũng không sửa được |

---

## 2. Quy ước code

- Python 3.12, type hint đầy đủ, `from __future__ import annotations`.
- SQLAlchemy 2.x style: `Mapped[...]` + `mapped_column(...)`. Không dùng `Column()` kiểu cũ.
- Không dùng `session.execute(text(...))` với chuỗi nối tay. Tham số luôn bind.
- Jinja2 autoescape bật. Không dùng `|safe` với dữ liệu người dùng nhập.
- Mọi form POST có CSRF token.
- Comment giải thích **tại sao**, không giải thích **cái gì**.
- `ruff check .` phải sạch trước khi commit.

### Cấu trúc thư mục

```
app/
  models.py          23 bảng. KHÔNG tách file.
  enums.py           tập giá trị cố định + ma trận quyền mặc định
  db.py              Base, mixin, helper ràng buộc
  config.py          đọc biến môi trường
  core/
    crypto.py        AES-256-GCM
    reveal.py        cổng xem mật khẩu
    security.py      băm Argon2id          <- sẽ viết
    permissions.py   dependency RBAC       <- sẽ viết
    audit.py         ghi audit log         <- sẽ viết
  services/          logic nghiệp vụ, KHÔNG gọi DB từ route
  routers/           endpoint FastAPI, mỏng
  templates/
alembic/versions/
tests/
scripts/
```

---

## 3. Phân quyền (RBAC)

FastAPI không có sẵn, phải tự xây. Mô hình: `users` → `roles` → `role_permissions`
(module, action), cộng `user_permission_overrides` để Admin chỉnh quyền lẻ.

**Mặc định là từ chối.** Dependency kiểm quyền gắn ở cấp router; endpoint nào
không khai báo `require(module, action)` thì không ai vào được. Không bao giờ
viết endpoint mở rồi "để sau thêm quyền".

Thiếu quyền trả **403** với thông báo chung. Không được tiết lộ bản ghi có tồn
tại hay không, không trả tên trường, không trả câu SQL.

Ma trận quyền mặc định ở `app/enums.py:DEFAULT_ROLE_PERMISSIONS`. Sửa ở đó rồi
chạy lại seed, không hardcode trong route.

---

## 4. Audit log

Ghi một dòng cho: CREATE, UPDATE, DELETE, RESTORE, LOGIN, LOGIN_FAIL, REVEAL.

`before_after` **không bao giờ** được chứa giá trị của các cột trong
`app/models.py:REDACTED_FIELDS` (`pc_password_enc`, `email_password_enc`,
`license_key_enc`, `password_hash`). Lọc trước khi ghi, không lọc khi hiển thị.

---

## 5. Mật khẩu nhân viên — TUYỆT ĐỐI

Người dùng của hệ thống này yêu cầu lưu mật khẩu PC/email của nhân viên. Thiết
kế dưới đây là điều kiện để việc đó không biến thành sự cố bảo mật. Mọi điểm
đều bắt buộc.

**Lưu trữ**

- Mật khẩu nằm ở bảng riêng `person_secrets`, không nằm trong `persons`.
- Mã hoá AES-256-GCM qua `app/core/crypto.py`. Không giải mã ở nơi khác.
- AAD = `(bảng, khoá chính, tên cột)` — chống chép bản mã sang bản ghi khác.
- Khoá nạp từ biến môi trường `ITAM_SECRET_KEY_V1`, lấy từ Windows Credential
  Manager. **Không hardcode. Không commit. Không ghi ra log.**

**CẤM TUYỆT ĐỐI**

- ❌ Thêm cột mật khẩu dạng chữ thường vào bất kỳ bảng nào.
- ❌ Đưa cột `*_enc` vào response, template, CSV export, log, hay `print()`.
- ❌ Trả giá trị đã giải mã từ bất kỳ endpoint nào ngoài
  `POST /persons/{id}/secrets/reveal`.
- ❌ Trả mật khẩu trong API danh sách "cho tiện frontend".
- ❌ Bỏ qua bước xác minh lại mật khẩu vì thấy phiền khi test.
- ❌ Hardcode khoá vào code để chạy thử rồi định bỏ ra sau.

**Luồng xem (FR-06), không được rút gọn**

1. Kiểm quyền `(secrets, view)` — chỉ Admin có.
2. Màn hình luôn hiện `••••••` (dùng `app.core.reveal.mask`).
3. Bấm "Xem" → nhập lại mật khẩu **đăng nhập của chính mình**.
4. Đúng → `RevealGate.authorize()` cấp token sống 2 phút.
5. Trình duyệt tự ẩn lại sau 60 giây.
6. Mỗi lần giải mã thành công → một dòng audit `REVEAL`.
7. Sai 5 lần trong 15 phút → khoá 15 phút.

Logic đã viết sẵn ở `app/core/reveal.py` và có test. Route chỉ gọi vào đó.

---

## 6. Vận hành

- **Không bao giờ** đặt chuỗi kết nối production vào môi trường mà agent chạy được.
  Dev dùng PostgreSQL local, production dùng PostgreSQL online, hai file cấu hình.
- Chạy `pytest` trước mỗi lần commit.
- Commit sau mỗi module hoàn chỉnh, thông điệp mô tả thay đổi nghiệp vụ.
- Không `pip install` thêm thư viện nếu không có trong `requirements.txt` mà
  chưa hỏi.
- Không tự refactor những module đang chạy ổn khi không được yêu cầu.

---

## 7. Thứ tự làm việc

| Giai đoạn | Nội dung | Điều kiện sang bước sau |
| --- | --- | --- |
| ✅ Nền | models, migration, crypto, reveal, test ràng buộc | `pytest` xanh (đã đạt) |
| 1 | `security.py` (Argon2id), `permissions.py`, `audit.py`, đăng nhập, SQLAdmin | Test RBAC cho cả 3 vai trò xanh |
| 2 | **Tài sản + Mượn–trả** làm xuyên suốt: service → route → template | IT dùng thử 30 phút với dữ liệu thật và xác nhận |
| 3 | Nhân sự + màn hình mật khẩu | Test luồng reveal xanh |
| 4 | License, Thẻ ra vào, Hợp đồng | — |
| 5 | Phone List, tìm kiếm toàn cục, i18n, trang tổng quan | — |

**Giai đoạn 2 là chốt chặn quan trọng nhất.** Làm một module xuyên suốt và để
người dùng xác nhận trước khi nhân bản pattern ra các module còn lại. Lần trước
dự án đã làm hết rồi mới phát hiện không khớp nghiệp vụ.

---

## 8. Khi gặp nghi vấn

- Yêu cầu mâu thuẫn với một bất biến ở trên → **dừng và hỏi**, không tự quyết.
- Thiếu thông tin nghiệp vụ → hỏi, không tự bịa giá trị mặc định.
- Thấy một quy tắc ở đây có vẻ thừa → nó đến từ một lỗi có thật trong file Excel
  hiện tại. Đọc `docs/BRD.md` mục "Hiện trạng và painpoint" trước khi đề nghị bỏ.
