# Dọn master data, loại nhân sự, mã thiết bị, Kho mật khẩu — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ẩn ID khỏi giao diện, bỏ mã phòng ban và mã tem GA, đổi PC name thành Mã thiết bị bắt buộc, thêm loại nhân sự với mã tự cấp, chuyển danh mục phần mềm vào Sổ tổng, làm gọn Kho mật khẩu.

**Architecture:** Một migration `0007` đổi schema và phân loại 6 người chưa có mã. Logic mã nhân sự trong service mới `app/services/person_code_service.py`, gọi từ `PersonAdmin.on_model_change`. Danh mục phần mềm dùng chung cơ chế nhãn với màu (`mark_service`, tiền tố `SW-`). Kho mật khẩu viết lại template `person_secrets.html` theo hướng A.

**Tech Stack:** FastAPI, SQLAlchemy 2.0, PostgreSQL, Alembic, SQLAdmin 0.20, Tabulator 6.3.1, Jinja2.

**Spec:** `docs/superpowers/specs/2026-11-09-don-master-data-va-kho-mat-khau-design.md`

## Global Constraints

- `venv\Scripts\pytest.exe -q` và `venv\Scripts\ruff.exe check .` sạch sau mỗi task; không chạy hai pytest song song.
- Không chạy `alembic` / `uvicorn` / script import `app.db` với `.env` mặc định (Aiven). Chạy thử thì đặt `ITAM_DATABASE_URL` tới DB local tên chứa `test`.
- Không bỏ cột `id` khỏi database; chỉ ẩn khỏi hiển thị.
- Nhãn hiển thị mã thiết bị: "Mã thiết bị" / "Device code" / 「機器コード」. Loại nhân sự: "Nhân viên chính thức" / "Employee" / 「正社員」, "Vendor" / "Vendor" / 「ベンダー」, "Công tác Nhật" / "Japan business trip" / 「日本出張者」.
- ENUM `person_type`: `EMPLOYEE`, `VENDOR`, `BUSINESS_TRIP`. Mã tự cấp `VND-001`, `JP-001` (3 chữ số tối thiểu).
- Đổi schema thì cập nhật `app/models.py`, `docs/database.dbml` (giữ nguyên chữ "a" thừa người dùng chưa commit — chỉ stage phần mình sửa), `tests/test_schema_cleanup.py`, `CLAUDE.md` ("hiện tới `0007`").
- Mọi ghi dữ liệu có audit; `REDACTED_FIELDS` không lọt ra trang Kho mật khẩu mới.
- Test viết trước, xem đỏ. Commit mỗi task, không push.

## Review Focus

1. Tài sản cũ (mọi trang: Sổ tổng, chi tiết, tìm kiếm, thùng rác, CSV, bàn giao) vẫn mở được sau khi bỏ `asset_code` — không còn tham chiếu sót. (Task 1: test HTTP mở từng trang trả 200.)
2. Tạo vendor hai lần liên tiếp, hoặc sau khi xóa mềm `VND-002` → mã không trùng, không cấp lại mã đã xóa. (Task 2.)
3. Mã thiết bị trùng khác hoa thường (`tky-pc0001`) hoặc rỗng khi sửa trên Sổ tổng / form → 400 có thông báo. (Task 4.)
4. Trang Kho mật khẩu mới không chứa chuỗi bản mã (`CIPHERTEXT`) hay giá trị đã giải mã; người chỉ xem không thấy nút mắt / sửa. (Task 6.)
5. Xóa một mục phần mềm đang gắn trên máy → máy mất mục đó, nhãn màu vẫn còn. (Task 5.)

---

### Task 1: Migration 0007 và đổi tên trong toàn bộ code

**Files:**
- Create: `alembic/versions/0007_master_data_cleanup.py`
- Modify: `app/models.py`, `app/enums.py` (thêm `PersonType`), `app/admin.py`, `app/routers/{global_search,trash,assets}.py`, `app/services/{ledger_service,assignment_service}.py`, `scripts/cleanup_excel_import.py`, `templates/sqladmin/{so_tong,details,global_search,asset_actions_modal}.html`, `app/core/i18n.py`, `docs/database.dbml`, `CLAUDE.md`, tests đang dùng `pc_name` / `asset_code` / `Department.code`
- Test: `tests/test_schema_cleanup.py`, `tests/test_master_data.py` (mới)

**Interfaces:**
- Produces: `Asset.device_code: Mapped[str]` (NOT NULL, `uq_alive_assets_device_code`); không còn `Asset.asset_code`, `Asset.pc_name`, `Department.code`; `Person.person_type: Mapped[PersonType]` (NOT NULL, default `EMPLOYEE`); `Person.staff_code: Mapped[str]` NOT NULL. Ledger row key `"pc_name"` đổi thành `"device_code"`, bỏ `"asset_code"`.

- [ ] **Step 1: Failing tests.** `tests/test_schema_cleanup.py` thêm: `test_assets_have_device_code_only` (cột `device_code` NOT NULL; không có `asset_code`, `pc_name`), `test_departments_have_no_code`, `test_persons_have_type_and_required_code` (`person_type` NOT NULL, `staff_code` NOT NULL), `test_person_type_enum_values` (`pg_enum` của `person_type` = `{EMPLOYEE, VENDOR, BUSINESS_TRIP}`), `test_device_code_unique_index_exists`. Cập nhật `tests/conftest.py` seed: `Asset(device_code="TKY-PC0001", serial="SN-0001", ...)`, `Department(name_en="Production")`, mọi `Person` có `staff_code`. `tests/test_master_data.py::test_pages_open_after_cleanup` (admin_client): `/admin/so-tong`, `/admin/api/so-tong`, `/admin/asset/list`, `/admin/asset/details/{id}`, `/admin/person/list`, `/admin/department/list`, `/admin/global-search?q=TKY`, `/admin/trash`, `/admin/person-secret/list` đều 200 (Review Focus 1).
- [ ] **Step 2: Run** — FAIL.
- [ ] **Step 3: Migration `0007`** (`down_revision="0006"`):
  - Dừng với `RuntimeError` rõ ràng nếu còn `assets.asset_code IS NOT NULL` hoặc `assets.pc_name IS NULL` (kể cả xóa mềm).
  - Bỏ index + cột `assets.asset_code`; bỏ CHECK `ck_assets_has_some_identifier`; đổi `pc_name` → `device_code`, đổi index `uq_alive_assets_pc_name` → `uq_alive_assets_device_code`, đặt NOT NULL.
  - Bỏ index `uq_alive_departments_code` và cột `departments.code`.
  - Tạo ENUM `person_type`, thêm `persons.person_type` NOT NULL default `'EMPLOYEE'`.
  - Phân loại theo email (không phân biệt hoa thường), sắp theo `full_name`, chỉ những người `staff_code IS NULL`:
    VENDOR: `l.hoangduc.rr@tokuyamagr.com`, `m.hoangthi.h7@tokuyamagr.com`, `k.lenguyennhat.9x@tokuyamagr.com`;
    BUSINESS_TRIP: `h.asada@tokuyama.com.vn`, `h.sugimoto.ph@tokuyamagr.com`, `a.takeda.sc@tokuyamagr.com`.
    Người thiếu mã còn lại → VENDOR. Cấp mã `VND-NNN` / `JP-NNN` tiếp theo theo thứ tự `full_name`, rồi `staff_code` NOT NULL. In (`print`) danh sách người được cấp mã.
  - `downgrade()`: `raise NotImplementedError` (đã bỏ dữ liệu cột).
- [ ] **Step 4: Đổi code:** model, enum `PersonType`, mọi tham chiếu `pc_name` → `device_code`, bỏ `asset_code` (Sổ tổng cột + ô sửa, `ASSET_TEXT_FIELDS`, `humanize_error_str`, trash kiểm trùng, global search, details, modal bàn giao, CSV, `assignment_service` thông báo), bỏ `Department.code` (view, i18n, `__str__`). Nhãn theo Global Constraints. `docs/database.dbml` cập nhật.
- [ ] **Step 5: Diễn tập** trên bản khôi phục local của `C:\Users\hungm\itam-backups\aiven-before-0006-*.dump` (DB `itam_test_rehearse`): `alembic upgrade head` thành công, 71 tài sản đều có `device_code`, 6 người nhận `VND-001..003` / `JP-001..003` đúng loại, `alembic check` sạch. Xóa DB tạm.
- [ ] **Step 6: Run** `pytest -q`, `ruff` — PASS. **Commit** `refactor(db): ma thiet bi, bo ma GA va ma phong ban, loai nhan su`

### Task 2: Mã nhân sự tự cấp và kiểm tra theo loại

**Files:** Create `app/services/person_code_service.py`, `tests/test_person_codes.py`; Modify `app/admin.py` (`PersonAdmin`), `app/services/ledger_service.py` (cột loại), `templates/sqladmin/so_tong.html` (cột + lọc loại).

**Interfaces:**
- Produces: `PREFIX = {PersonType.VENDOR: "VND-", PersonType.BUSINESS_TRIP: "JP-"}`; `next_code(db: Session, person_type: PersonType) -> str`; `resolve_code(db: Session, person_type: PersonType, code: str | None) -> str` (trả mã cuối cùng hoặc `ValueError`). Ledger row thêm `"person_type"`.

- [ ] **Step 1: Failing tests** (`tests/test_person_codes.py`):
  - `test_next_vendor_code_starts_at_001` → `"VND-001"`; sau khi có `VND-001` và `VND-007` (đã xóa mềm) → `"VND-008"` (Review Focus 2).
  - `test_next_code_ignores_hand_typed_codes_not_matching_pattern` (`VND-ABC` có sẵn → vẫn `VND-001`).
  - `test_resolve_code` parametrize: `(EMPLOYEE, None) → ValueError`; `(EMPLOYEE, "VND-001") → ValueError`; `(EMPLOYEE, "JP-004") → ValueError`; `(EMPLOYEE, "TVC00099") → "TVC00099"`; `(VENDOR, None) → "VND-001"`; `(VENDOR, "TVC00099") → ValueError`; `(BUSINESS_TRIP, "JP-010") → "JP-010"`.
  - `test_person_form_assigns_code_for_vendor`: `PersonAdmin().on_model_change({"full_name": "X", "person_type": "VENDOR", "staff_code": None, ...}, Person(), True, DummyRequest(...))` → `data["staff_code"] == "VND-001"`.
  - `test_person_form_refuses_employee_without_code` → `ValueError`.
  - `test_ledger_row_has_person_type`.
- [ ] **Step 2: Run** — FAIL. **Step 3: Implement**; `PersonAdmin.on_model_change` gọi `resolve_code` và gán `data["staff_code"]`. Cột "Loại nhân sự" ở danh sách nhân sự và Sổ tổng (`headerFilter: 'list'`, ba nhãn). **Step 4: Run** `pytest -q`, `ruff`. **Commit** `feat(person): loai nhan su va ma tu cap`

### Task 3: Ẩn ID, gỡ mã phòng ban khỏi giao diện, ẩn menu Nhãn tài sản, audit hiện tên

**Files:** Modify `app/admin.py` (mọi `column_list` / `column_details_list` / `column_searchable_list` / `column_sortable_list`, đăng ký menu), `templates/sqladmin/{details,list,trash,global_search}.html` nếu có in id, `AuditLogAdmin` formatter; Test `tests/test_master_data.py`.

**Interfaces:** Produces: `AuditLogAdmin` cột "Bản ghi" hiện `device_code` / `staff_code` + tên / tên danh mục; rơi về `#id` khi không tra được.

- [ ] **Step 1: Failing tests:** `test_no_view_lists_id_column` — với mỗi view trong `app.state.admin._views`, `"id"` không nằm trong tên cột `column_list` / `column_details_list` (dùng `view._list_prop_names` hoặc `get_list_columns()`; kiểm `name != "id"` và `!= "person_id"` cho PersonSecret); `test_sidebar_has_no_asset_tag_link` — HTML `/admin/so-tong` không chứa `/admin/asset-tag/list`; `test_audit_record_shows_device_code` — tạo `AuditLog(table_name="assets", record_id=asset.id, ...)`, trang `/admin/audit-log/list` chứa `TKY-PC0001`.
- [ ] **Step 2: Run** — FAIL. **Step 3: Implement.** Ẩn menu bằng cách bỏ view khỏi `admin._menu` sau khi `add_view` (giữ route để không vỡ link cũ) hoặc cách tương đương của SQLAdmin 0.20. **Step 4: Run**, **Commit** `feat(ui): an cot ID, an menu nhan tai san`

### Task 4: Mã thiết bị sửa được trên Sổ tổng

**Files:** Modify `app/services/ledger_service.py` (`ASSET_TEXT_FIELDS` thêm `device_code` 50 ký tự, bắt buộc), `templates/sqladmin/so_tong.html` (cột editable khi `PERMS.assets`); Test `tests/test_so_tong_edit.py`.

- [ ] **Step 1: Failing tests:** `test_edit_device_code_saved_and_audited`; `test_device_code_cannot_be_blank` → 400; `test_device_code_duplicate_ignoring_case` (`"tky-pc0001"` khi đã có `TKY-PC0001` ở máy khác) → 400 (Review Focus 3). Mỗi request 400 là một test riêng (400 làm rollback dữ liệu seed). Form SQLAdmin: `test_asset_form_refuses_blank_device_code`.
- [ ] **Step 2–4:** Run FAIL, implement, run PASS. **Commit** `feat(so-tong): sua ma thiet bi`

### Task 5: Danh mục phần mềm trong hộp quản lý trên Sổ tổng

**Files:** Modify `app/services/mark_service.py` (tổng quát hóa theo tiền tố), `app/routers/so_tong.py`, `templates/sqladmin/so_tong.html`; Test `tests/test_marks.py`.

**Interfaces:**
- Produces: `create_software(db, name, user_id, ip_address) -> AssetTag` (mã `SW-…` sinh từ tên như `_new_code`, không cần màu), `update_software(db, tag_id, name, ...)`, `delete_software(db, tag_id, ...) -> int`; API `POST /admin/api/so-tong/software-catalog`, `PATCH|DELETE /admin/api/so-tong/software-catalog/{tag_id}` trả `{"success": True, "software": list_software_tags(db)}`; quyền ghi `assets:change`.

- [ ] **Step 1: Failing tests:** tạo / đổi tên / xóa phần mềm qua API; tên trùng → 400; xóa phần mềm đang gắn trên máy → link bị gỡ, mark màu trên máy đó vẫn còn (Review Focus 5); người chỉ xem → 403; `set_asset_mark` không nhận tag `SW-` (đã có), `set_asset_software` không nhận tag `MARK-`.
- [ ] **Step 2–4:** Run FAIL, implement (hộp "Quản lý" có hai phần Màu / Phần mềm; danh sách phần mềm ở panel cập nhật sau khi sửa), run PASS. Browser check trên DB local. **Commit** `feat(so-tong): quan ly danh muc phan mem`

### Task 6: Kho mật khẩu — hướng A

**Files:** Modify `templates/sqladmin/person_secrets.html` (viết lại phần trình bày, giữ nguyên các lời gọi API `/admin/person-secret/save`, `/admin/person-secret/{id}/reveal`, `/admin/person-secret/reveal/revoke` và luồng xác thực lại), `app/admin.py` (`PersonSecretAdmin` context nếu cần thêm `person_type` / đếm); Test `tests/test_secrets_api.py` hoặc `tests/test_master_data.py`.

- [ ] **Step 0:** Load skill `frontend-design` (người dùng yêu cầu).
- [ ] **Step 1: Failing tests:** trang `/admin/person-secret/list` (admin) chứa `id="vaultSearch"`, ba chip lọc (`data-filter="all|missing_pc|missing_email"`), tiêu đề "Kho mật khẩu", không chứa "AES-256-GCM"; với `PersonSecret(pc_password_enc=b"\x01CIPHERTEXT")` trang không chứa `CIPHERTEXT` (Review Focus 4); viewer không có quyền `secrets:change` → không có nút sửa (`data-action="edit"`) và không có nút mắt cho người không có `secrets:view`.
- [ ] **Step 2: Run** — FAIL. **Step 3: Implement** theo spec mục 6: tiêu đề một dòng + "N / M người đã lưu"; ô tìm; chip Tất cả / Thiếu PC / Thiếu Email; bảng 3 cột (Nhân sự với dòng phụ mã · phòng ban hoặc loại; PC; Email) với nhãn "✓ Đã lưu" / "— Chưa có" và nút mắt; bấm dòng mở hộp sửa; một nút "Khóa phiên" nhỏ ở góc; dòng chú thích cuối bảng "Mỗi lần xem mật khẩu đều được ghi lại."; ba ngôn ngữ; điện thoại thành danh sách thẻ. Tên người đưa vào DOM bằng `textContent`.
- [ ] **Step 4: Run** `pytest -q`, `ruff`. **Browser check** (DB local, khổ rộng và iframe 390px): tìm, lọc, xem mật khẩu qua cổng xác thực, sửa, khóa phiên, không lỗi console. **Commit** `feat(vault): giao dien gon cho kho mat khau`

### Task 7: Tài liệu

- [ ] `HANDOVER.md` thêm mục 3h (thay đổi, migration `0007`, thứ tự lên production: sao lưu → `alembic upgrade head` → merge `main` vào `master`, chờ Render "Deploy live" → kiểm tra; khoảng một phút lỗi giữa migration và deploy). **Commit** `docs: ban giao dot don master data`

## Đưa lên production

Người dùng cho phép làm một mạch. Migration `0007` xóa vĩnh viễn cột `departments.code` (8 giá trị) nên người dùng tự chạy lệnh migration; agent làm sao lưu, merge `master`, kiểm tra.
