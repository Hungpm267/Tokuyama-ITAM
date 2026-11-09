# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Web app nội bộ quản lý laptop và nhân sự của Tokuyama Vietnam (ITAM), thay cho sheet Excel "List of TVC Employees". Đã thu hẹp phạm vi: hợp đồng, license, thẻ, danh bạ, dashboard, ma trận quyền được gỡ khỏi code (bản đầy đủ ở git tag `v1-full`), các bảng tương ứng bị xóa ở migration `0005`. 3 mã vai trò `ADMIN`, `GA_MANAGER`, `EXECUTIVE`, nhưng chỉ còn hai mức: Admin và chỉ xem. Giao diện ba ngôn ngữ (vi / en / ja). Người dùng trao đổi bằng tiếng Việt; comment và thông báo trong code cũng bằng tiếng Việt.

**Đọc trước khi sửa code:** `HANDOVER.md` (trạng thái hiện tại, các việc còn tồn chờ người dùng quyết định). Yêu cầu nghiệp vụ gốc ở `docs/BRD.md`; thiết kế từng tính năng ở `docs/superpowers/specs/`.

## Lệnh

Windows, venv ở `venv\` (Python 3.14 trên máy dev; Dockerfile và `render.yaml` dùng 3.12).

```powershell
venv\Scripts\pytest.exe -q                                   # toàn bộ test
venv\Scripts\pytest.exe tests\test_wave5_logic_audit.py -q   # một file
venv\Scripts\pytest.exe tests\test_secrets.py -k reveal -q   # một test theo tên
venv\Scripts\ruff.exe check .                                # lint, phải sạch trước khi commit
venv\Scripts\uvicorn.exe app.main:app --reload --port 8000   # chạy app -> http://localhost:8000/admin
venv\Scripts\python.exe -m alembic upgrade head              # áp migration lên DB trong ITAM_DATABASE_URL
venv\Scripts\python.exe -m alembic revision --autogenerate -m "..."
venv\Scripts\python.exe -m scripts.seed                      # seed vai trò, quyền mặc định, admin đầu tiên
```

Test cần PostgreSQL tại `127.0.0.1:5432` (user `postgres`). Fixture trong `tests/conftest.py` xóa rồi tạo lại database `itam_test` và chạy `alembic upgrade head`, nên **không chạy hai phiên pytest song song**. Fixture từ chối chạy nếu `ITAM_ENV=prod` hoặc tên database không chứa `test`.

**`.env` trỏ tới database PostgreSQL trên Aiven (không phải local), dù `ITAM_ENV=dev`.** Chạy `uvicorn`, `alembic` hay bất kỳ script nào import `app.db` là đụng vào database đó. Không kết nối, không chạy migration, không sửa dữ liệu ở đó khi người dùng chưa cho phép rõ ràng. Không in nội dung `.env`.

Không tự `git push` khi người dùng chưa bảo. Không `pip install` thư viện ngoài `requirements.txt` khi chưa hỏi.

## Kiến trúc

FastAPI + SQLAlchemy 2.0 (`Mapped[...]`) + PostgreSQL + Alembic. Gần như toàn bộ giao diện là **SQLAdmin 0.20** với template Jinja2 ghi đè trong `templates/sqladmin/`.

### Giao diện người dùng thật sự đi qua `app/admin.py`

`app/admin.py` (~3.500 dòng) chứa mọi `ModelView`, backend đăng nhập (`AdminAuth`), dashboard (`TokuyamaAdmin.index`) và phần lớn luật nghiệp vụ. Điều quan trọng nhất cần biết:

- **Sổ tổng** (`/admin/so-tong`, `routers/so_tong.py`, `services/ledger_service.py`, `templates/sqladmin/so_tong.html`, Tabulator trong `static/vendor/`) là màn hình chính; sửa ô đi qua `ledger_service`. Bàn giao / thu hồi đi qua `assignment_service`.
- **Form SQLAdmin không gọi tầng service.** Tạo / sửa qua form có luật riêng trong `on_model_change` / `after_model_change` của view. Khi thêm một luật nghiệp vụ, phải kiểm cả form và `ledger_service`.
- **Hình dạng dữ liệu trong hook của SQLAdmin:** `data` chứa trường quan hệ dưới dạng chuỗi khóa chính (`"asset": "5"`), ENUM dưới dạng tên thành viên (`"IN_STOCK"`), ô trống của cột nullable là `None`. Trong `on_model_change`, `model` còn mang giá trị **trước** khi sửa. Dùng các helper `_pk_of`, `_form_fk`, `_enum_of`. Gán thêm khóa vào `data` (vd. `data["contract_id"]`) thì SQLAdmin sẽ `setattr` lên bản ghi.
- **`after_model_change` chạy sau khi bản ghi chính đã commit**, trong một `SessionLocal()` khác. Các bước đồng bộ ở đó (trạng thái máy / thẻ, tiến độ hợp đồng, audit) được bọc try/except và ghi log. Giá trị "trước khi sửa" được chuyển từ `on_model_change` sang qua `request.state.itam_*`.
- **`BaseAdminView`** lo phần chung cho mọi view: phân quyền theo ma trận, lọc `is_deleted`, xóa mềm trong `delete_model` (kèm các chặn xóa khi còn đang dùng), cắt khoảng trắng, kiểm trùng không phân biệt hoa-thường (`unique_text_fields`), tự điền `created_by` / `updated_by`, audit trước / sau, xuất CSV, cache đếm bản ghi 30 giây (`_MODEL_COUNT_CACHE`, khóa theo model + bộ lọc — nhớ `invalidate_model_count_cache` khi ghi từ router).
- **`AliveOnlyModelConverter`** lọc bản ghi đã xóa mềm khỏi ô chọn quan hệ, nhưng trên form sửa vẫn giữ giá trị bản ghi đang trỏ tới (thiếu nó, lần lưu kế tiếp âm thầm trỏ sang dòng đầu tiên).
- Request hiện tại lấy qua `current_request_ctx` (ContextVar do `RequestContextMiddleware` đặt), dùng trong formatter và property `can_create/can_edit/can_delete`.

### Phân quyền và phiên

- Quyền `(module, action)` lưu ở `role_permissions`, mặc định ở `app/enums.py:DEFAULT_ROLE_PERMISSIONS`; không còn màn hình sửa. Mặc định là từ chối. Router kiểm bằng `has_permission()`; template và formatter dùng `can(request, module, action)` / `can_loan(request)`. Không kiểm theo tên vai trò.
- Có **hai `SessionMiddleware` lồng nhau**: của app (cookie `session`) và của SQLAdmin (cookie `admin_session`). Danh tính thật nằm ở cookie ký `itam_session` (`app/core/security.py`), hết hạn sau 30 phút không thao tác và được `sliding_session_middleware` trong `app/main.py` gia hạn. `AdminAuth.authenticate` thử cookie trước rồi mới tới token trong session.
- Ngôn ngữ: luôn dùng `get_current_lang(request)` / `_request_lang(request)` (cookie `itam_lang` trước), không đọc `session["lang"]`.
- Đăng nhập chỉ chấp nhận 3 mã vai trò hệ thống.

### Dữ liệu

- `app/models.py` là nguồn sự thật duy nhất của schema; đổi schema chỉ qua Alembic (`alembic/versions/`, hiện tới `0007`, 12 bảng; sơ đồ ở `docs/database.dbml`, đổi schema thì cập nhật cả file này). Trạng thái là ENUM native của PostgreSQL, lưu theo `.value`.
- Xóa là xóa mềm (`is_deleted`, bắt buộc `delete_reason`, có CHECK ở DB). Ràng buộc duy nhất là partial unique index `WHERE is_deleted = false` (`alive_unique`); "chỉ một bản ghi đang mở" là partial index `WHERE <cột đóng> IS NULL` (`one_open_per`) — xem `app/db.py`.
- Lịch sử `assignments` không xóa, chỉ đóng bằng ngày kết thúc; dòng đã đóng không được đổi máy / người. `audit_logs` chỉ INSERT / SELECT, có trigger DB chặn.
- `assets.status` phải khớp với lượt bàn giao đang mở: `IN_USE` chỉ sinh ra qua bàn giao, không gõ tay (`_sync_asset_status`).
- "Hôm nay" là `app/core/clock.py:today_local()` (UTC+7), không dùng `date.today()` — máy chủ cloud chạy UTC. Hiển thị thời gian qua `format_datetime_clean`.
- Phần mềm trên máy là nhãn `asset_tags` có mã bắt đầu `SW-`, không phải thiết bị. Loại tài sản mang tên phần mềm bị từ chối.

### Mật khẩu nhân viên (FR-06) — vùng không được nới lỏng

Nằm ở bảng riêng `person_secrets`, mã hóa AES-256-GCM với AAD `(bảng, khóa chính, cột)` trong `app/core/crypto.py`; khóa lấy từ biến môi trường `ITAM_SECRET_KEY_V1`. Chỉ `POST /persons/{id}/secrets/reveal` (và alias trong `routers/secrets.py`) được trả giá trị đã giải mã, sau khi Admin nhập lại mật khẩu của chính mình qua `RevealGate` (`app/core/reveal.py`: token 2 phút, sai 5 lần khóa 15 phút, mỗi lần xem ghi audit `REVEAL`). Các cột trong `models.REDACTED_FIELDS` không bao giờ xuất hiện trong response, template, CSV, log hay audit (`record_audit` tự che).

### Endpoint nhận JSON

Dùng `app/core/inputs.py` (`read_json_object`, `require_positive_int`, `optional_text`) thay cho `await request.json()` + `int(...)` trần: body có thể là mảng, và `int(True) == 1` sẽ thao tác nhầm lên bản ghi số 1.

## Test

Test là hợp đồng: test đỏ nghĩa là code mới sai, không sửa hay xóa test để cho qua. Mỗi test chạy trong một transaction rồi rollback (fixture `db`, dữ liệu mẫu ở fixture `seed`).

Hai kiểu test dùng trong repo:

- Gọi thẳng hook với `DummyRequest`: `asyncio.run(SomeAdmin().on_model_change(data, model, is_created, DummyRequest(session={...}, db=db)))`. `_get_admin_db(request)` sẽ dùng `request.state.db`.
- Đi qua HTTP bằng `TestClient(app)`: cần fixture autouse `override_db` (chép từ `tests/test_wave5_logic_audit.py`) thay `get_db`, `app.admin.SessionLocal` và `session_maker` của từng view bằng session của test, đồng thời xóa cache đếm và cache user. Đăng nhập bằng cách đặt cookie `itam_session` từ `create_session_token`.

Khi sửa lỗi: viết test tái hiện trước, xem nó đỏ, rồi mới sửa.
