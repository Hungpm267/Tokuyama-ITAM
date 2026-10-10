# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Web app nội bộ quản lý tài sản IT của Tokuyama Vietnam (ITAM), thay cho các file Excel. 5 người dùng, 3 vai trò: `ADMIN`, `GA_MANAGER`, `EXECUTIVE`. Giao diện ba ngôn ngữ (vi / en / ja). Người dùng trao đổi bằng tiếng Việt; comment và thông báo trong code cũng bằng tiếng Việt.

**Đọc trước khi sửa code:** `GEMINI.md` (bất biến của dự án — vẫn có hiệu lực với mọi agent) và `HANDOVER.md` (trạng thái hiện tại, các việc còn tồn chờ người dùng quyết định). Yêu cầu nghiệp vụ gốc ở `docs/BRD.md`; thiết kế từng tính năng ở `docs/superpowers/specs/`.

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

- **Form SQLAdmin không gọi tầng service.** Chỉ các thao tác có router riêng mới đi qua service: bàn giao / thu hồi máy (`routers/assets.py` → `assignment_service`), nhập kho theo lô (`routers/batch_receive.py`), nhận phần mềm (`routers/software_receive.py` → `license_service.receive_license_for_line`). Mọi tạo / sửa khác (License, Gán license, Mượn thẻ, Tài sản, Hợp đồng…) đi qua form, nên luật phải nằm trong `on_model_change` / `after_model_change` của view. `card_service`, `phone_service`, `person_service`, `asset_service` hiện chỉ có test gọi. Khi thêm một luật nghiệp vụ, phải đặt ở **cả hai** nơi.
- **Hình dạng dữ liệu trong hook của SQLAdmin:** `data` chứa trường quan hệ dưới dạng chuỗi khóa chính (`"asset": "5"`), ENUM dưới dạng tên thành viên (`"IN_STOCK"`), ô trống của cột nullable là `None`. Trong `on_model_change`, `model` còn mang giá trị **trước** khi sửa. Dùng các helper `_pk_of`, `_form_fk`, `_enum_of`. Gán thêm khóa vào `data` (vd. `data["contract_id"]`) thì SQLAdmin sẽ `setattr` lên bản ghi.
- **`after_model_change` chạy sau khi bản ghi chính đã commit**, trong một `SessionLocal()` khác. Các bước đồng bộ ở đó (trạng thái máy / thẻ, tiến độ hợp đồng, audit) được bọc try/except và ghi log. Giá trị "trước khi sửa" được chuyển từ `on_model_change` sang qua `request.state.itam_*`.
- **`BaseAdminView`** lo phần chung cho mọi view: phân quyền theo ma trận, lọc `is_deleted`, xóa mềm trong `delete_model` (kèm các chặn xóa khi còn đang dùng), cắt khoảng trắng, kiểm trùng không phân biệt hoa-thường (`unique_text_fields`), tự điền `created_by` / `updated_by`, audit trước / sau, xuất CSV, cache đếm bản ghi 30 giây (`_MODEL_COUNT_CACHE`, khóa theo model + bộ lọc — nhớ `invalidate_model_count_cache` khi ghi từ router).
- **`AliveOnlyModelConverter`** lọc bản ghi đã xóa mềm khỏi ô chọn quan hệ, nhưng trên form sửa vẫn giữ giá trị bản ghi đang trỏ tới (thiếu nó, lần lưu kế tiếp âm thầm trỏ sang dòng đầu tiên).
- Request hiện tại lấy qua `current_request_ctx` (ContextVar do `RequestContextMiddleware` đặt), dùng trong formatter và property `can_create/can_edit/can_delete`.

### Phân quyền và phiên

- Ma trận `(module, action)` trong `role_permissions`, cộng `user_permission_overrides`; mặc định ở `app/enums.py:DEFAULT_ROLE_PERMISSIONS`. Mặc định là từ chối. Router kiểm bằng `has_permission()` (`app/core/permissions.py`); template và formatter dùng `can(request, module, action)` / `can_loan(request)`. Không kiểm theo tên vai trò.
- Có **hai `SessionMiddleware` lồng nhau**: của app (cookie `session`) và của SQLAdmin (cookie `admin_session`). Danh tính thật nằm ở cookie ký `itam_session` (`app/core/security.py`), hết hạn sau 30 phút không thao tác và được `sliding_session_middleware` trong `app/main.py` gia hạn. `AdminAuth.authenticate` thử cookie trước rồi mới tới token trong session.
- Ngôn ngữ: luôn dùng `get_current_lang(request)` / `_request_lang(request)` (cookie `itam_lang` trước), không đọc `session["lang"]`.
- Đăng nhập chỉ chấp nhận 3 mã vai trò hệ thống.

### Dữ liệu

- `app/models.py` là nguồn sự thật duy nhất của schema; đổi schema chỉ qua Alembic (`alembic/versions/`, hiện tới `0003`). Trạng thái là ENUM native của PostgreSQL, lưu theo `.value`.
- Xóa là xóa mềm (`is_deleted`, bắt buộc `delete_reason`, có CHECK ở DB). Ràng buộc duy nhất là partial unique index `WHERE is_deleted = false` (`alive_unique`); "chỉ một bản ghi đang mở" là partial index `WHERE <cột đóng> IS NULL` (`one_open_per`) — xem `app/db.py`.
- Bảng lịch sử (`assignments`, `license_assignments`, `card_loans`) không xóa, chỉ đóng bằng ngày kết thúc; dòng đã đóng không được đổi máy / người / thẻ / license. `audit_logs` chỉ INSERT / SELECT, có trigger DB chặn.
- **Số lượng luôn được tính, không lưu.** Số đã nhận của hạng mục hợp đồng đi qua một hàm duy nhất `contract_service.line_received_qty`: hạng mục `HARDWARE` đếm thiết bị còn sống (`assets.contract_line_id`), hạng mục `SOFTWARE` cộng seat của các gói license còn sống (`licenses.contract_line_id`). `sync_contract_delivery_status` phải được gọi sau mọi thay đổi ảnh hưởng tới số đó (tạo / sửa / xóa / khôi phục thiết bị, gói license, hạng mục). Seat đã dùng của license cũng tính từ các lượt gán đang mở.
- `assets.status` và `access_cards.status` phải khớp với lượt mượn đang mở: `IN_USE` / `BORROWED` chỉ sinh ra qua nghiệp vụ bàn giao / mượn, không gõ tay (`_sync_asset_status`, `_sync_card_status`).
- "Hôm nay" là `app/core/clock.py:today_local()` (UTC+7), không dùng `date.today()` — máy chủ cloud chạy UTC. Hiển thị thời gian qua `format_datetime_clean`.
- Phần mềm / license **không** phải thiết bị: quản lý ở `license_products` / `licenses` / `license_assignments` và nhận hàng qua hạng mục hợp đồng loại Phần mềm. Loại tài sản mang tên phần mềm bị từ chối.

### Mật khẩu nhân viên (FR-06) — vùng không được nới lỏng

Nằm ở bảng riêng `person_secrets`, mã hóa AES-256-GCM với AAD `(bảng, khóa chính, cột)` trong `app/core/crypto.py`; khóa lấy từ biến môi trường `ITAM_SECRET_KEY_V1`. Chỉ `POST /persons/{id}/secrets/reveal` (và alias trong `routers/secrets.py`) được trả giá trị đã giải mã, sau khi Admin nhập lại mật khẩu của chính mình qua `RevealGate` (`app/core/reveal.py`: token 2 phút, sai 5 lần khóa 15 phút, mỗi lần xem ghi audit `REVEAL`). Các cột trong `models.REDACTED_FIELDS` không bao giờ xuất hiện trong response, template, CSV, log hay audit (`record_audit` tự che). Chi tiết bắt buộc ở `GEMINI.md` mục 5.

### Endpoint nhận JSON

Dùng `app/core/inputs.py` (`read_json_object`, `require_positive_int`, `optional_text`) thay cho `await request.json()` + `int(...)` trần: body có thể là mảng, và `int(True) == 1` sẽ thao tác nhầm lên bản ghi số 1.

## Test

Test là hợp đồng: test đỏ nghĩa là code mới sai, không sửa hay xóa test để cho qua. Mỗi test chạy trong một transaction rồi rollback (fixture `db`, dữ liệu mẫu ở fixture `seed`).

Hai kiểu test dùng trong repo:

- Gọi thẳng hook với `DummyRequest`: `asyncio.run(SomeAdmin().on_model_change(data, model, is_created, DummyRequest(session={...}, db=db)))`. `_get_admin_db(request)` sẽ dùng `request.state.db`.
- Đi qua HTTP bằng `TestClient(app)`: cần fixture autouse `override_db` (chép từ `tests/test_wave5_logic_audit.py`) thay `get_db`, `app.admin.SessionLocal` và `session_maker` của từng view bằng session của test, đồng thời xóa cache đếm và cache user. Đăng nhập bằng cách đặt cookie `itam_session` từ `create_session_token`.

Khi sửa lỗi: viết test tái hiện trước, xem nó đỏ, rồi mới sửa.
