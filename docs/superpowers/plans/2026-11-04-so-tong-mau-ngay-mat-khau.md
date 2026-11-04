# Sổ tổng: màu dòng, ngày bàn giao, cột mật khẩu, dọn ghi chú — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cho người dùng tự tô màu dòng có chú giải, sửa / xóa trống ngày bàn giao, thấy rõ loại mật khẩu đã lưu, và dọn ghi chú agent tự ghi khi nhập Excel.

**Architecture:** Kiểu đánh dấu là `asset_tags` có mã `MARK-…`, gắn qua `asset_tag_links`, logic trong service mới `app/services/mark_service.py`. Ngày bàn giao cho phép NULL qua migration `0006`, sửa từ Sổ tổng qua `ledger_service.update_cell`. Dọn dữ liệu là script chạy một lần `scripts/cleanup_excel_import.py`, có chạy thử.

**Tech Stack:** FastAPI, SQLAlchemy 2.0, PostgreSQL, Alembic, SQLAdmin 0.20, Tabulator 6.3.1 (vendored), Jinja2.

**Spec:** `docs/superpowers/specs/2026-11-04-so-tong-mau-ngay-mat-khau-design.md`

## Global Constraints

- Lệnh: `venv\Scripts\pytest.exe -q` và `venv\Scripts\ruff.exe check .` phải sạch sau mỗi task. Không chạy hai phiên pytest song song.
- KHÔNG chạy `alembic`, `uvicorn`, hay script import `app.db` với `.env` mặc định (trỏ Aiven). Chạy cục bộ thì đặt `ITAM_DATABASE_URL` tới DB local có tên chứa `test`.
- "Hôm nay" là `app/core/clock.py:today_local()`; endpoint JSON dùng `app/core/inputs.py`; không để lộ `REDACTED_FIELDS`.
- Mọi chữ hiển thị có ba ngôn ngữ vi / en / ja (`L(...)` trong template). Comment và thông báo lỗi bằng tiếng Việt.
- Mọi thay đổi dữ liệu ghi `record_audit(..., extra={"source": "so-tong"})`.
- Mã kiểu đánh dấu bắt đầu `MARK-`; mã phần mềm bắt đầu `SW-`. Màu dạng `#rrggbb`.
- Đổi schema thì cập nhật `app/models.py`, `docs/database.dbml`, `tests/test_schema_cleanup.py`, và dòng "hiện tới `0005`" trong `CLAUDE.md`.
- Test viết trước, chạy thấy đỏ, rồi mới viết code. Commit sau mỗi task (không push).

## Review Focus

1. Ngày nhập dạng `dd/mm/yyyy`, `yyyy-mm-dd`, chuỗi rác, `31/02/2026` → 400 có thông báo, không bao giờ 500. (Task 2)
2. Trang chi tiết máy / người có lượt bàn giao ngày NULL lẫn ngày thật → mở được, không lỗi sắp xếp `None` với `date`. (Task 1)
3. Tên kiểu đánh dấu chứa HTML (`<img src=x onerror=…>`) → hiện nguyên văn ở chú giải, ô và hộp quản lý, không chạy. Màu không phải `#rrggbb` → 400. (Task 4, Task 5)
4. Người chỉ có quyền xem gọi thẳng API đánh dấu / sửa ngày → 403, dữ liệu không đổi. (Task 2, Task 4)
5. Script dọn dữ liệu chạy hai lần → lần hai không đổi gì; dòng người dùng đã sửa không bị đụng. (Task 6)

---

### Task 1: Cho phép ngày bàn giao để trống (schema + hiển thị)

**Files:**
- Create: `alembic/versions/0006_assignment_date_optional.py`
- Modify: `app/models.py` (`Assignment.borrowed_at`), `templates/sqladmin/details.html:475`, `app/admin.py` (`AssignmentAdmin.on_model_change` quanh dòng 1775–1890), `app/services/ledger_service.py:140`, `docs/database.dbml`, `CLAUDE.md`
- Test: `tests/test_handover_date.py` (mới), `tests/test_schema_cleanup.py`

**Interfaces:**
- Produces: `Assignment.borrowed_at: Mapped[dt.date | None]`; ledger row `"borrowed_at"` là `"dd/mm/yyyy"` hoặc `None`.

- [ ] **Step 1: Write the failing tests** trong `tests/test_handover_date.py`:
  - `test_open_assignment_can_have_no_date(db, seed)`: tạo `Assignment(asset_id=seed["asset"].id, person_id=seed["person"].id, borrowed_at=None)`, `db.flush()` không lỗi.
  - `test_closed_assignment_without_start_date_is_allowed(db, seed)`: `borrowed_at=None, returned_at=dt.date(2026, 10, 1)` flush được (CHECK `returned_after_borrowed` cho qua khi NULL).
  - `test_ledger_shows_blank_date(db, seed)`: lượt mở ngày NULL → dòng `asset-{id}` có `borrowed_at is None`.
  - `test_detail_pages_render_with_mixed_dates(admin_client, db, seed)`: máy có một lượt đã đóng ngày `2026-09-01`→`2026-09-10` và một lượt mở ngày NULL; `GET /admin/asset/details/{id}` và `/admin/person/details/{person_id}` trả 200. (Review Focus 2; dùng fixture `admin_client`, `override_db` chép từ `tests/test_so_tong_edit.py`.)
  - `test_admin_form_saves_empty_date_as_null(db, seed)`: gọi `AssignmentAdmin().on_model_change({"asset": str(id), "person": str(pid), "borrowed_at": None, "returned_at": None}, Assignment(), True, DummyRequest(...))` không lỗi.
  - Trong `tests/test_schema_cleanup.py` thêm `test_borrowed_at_is_nullable(db)`: `inspect(...).get_columns("assignments")` → cột `borrowed_at` có `nullable is True`.

- [ ] **Step 2: Run** `venv\Scripts\pytest.exe tests\test_handover_date.py tests\test_schema_cleanup.py -q` — Expected: FAIL (NotNullViolation).

- [ ] **Step 3: Implement**
  - Migration `0006` (`down_revision = "0005"`): `op.alter_column("assignments", "borrowed_at", existing_type=sa.Date(), nullable=True)`. `downgrade()`: đặt lại NOT NULL (ghi chú trong docstring: sẽ lỗi nếu đã có ngày trống).
  - `models.py`: `borrowed_at: Mapped[dt.date | None] = mapped_column(Date, nullable=True)`.
  - `details.html:475`: sắp xếp không vỡ khi có `None` (vd. sắp theo `id` giảm dần, hoặc lọc ngày NULL ra cuối).
  - `AssignmentAdmin.on_model_change`: mọi so sánh với `b_at` chỉ chạy khi `b_at` không phải `None`; ô trống lưu NULL, không tự điền hôm nay.
  - `ledger_service.build_ledger_rows`: `assignment.borrowed_at.strftime(...) if assignment and assignment.borrowed_at else None`.
  - `database.dbml`: bỏ `not null` ở `assignments.borrowed_at`, note "Trống là không rõ ngày giao". `CLAUDE.md`: "hiện tới `0006`".

- [ ] **Step 4: Run** toàn bộ `venv\Scripts\pytest.exe -q` và `venv\Scripts\ruff.exe check .` — Expected: PASS, sạch.

- [ ] **Step 5: Commit** `feat(assignment): cho phep ngay ban giao de trong`

### Task 2: Sửa / xóa trống ngày bàn giao trên Sổ tổng

**Files:**
- Modify: `app/services/ledger_service.py` (`module_of_field`, `update_cell`), `templates/sqladmin/so_tong.html:190` (cột ngày), `tests/test_so_tong_edit.py:197` (bỏ `"borrowed_at"` khỏi danh sách ô không sửa được — yêu cầu đã đổi theo spec)
- Test: `tests/test_handover_date.py`

**Interfaces:**
- Consumes: Task 1.
- Produces: `PATCH /admin/api/so-tong/cell` nhận `field="borrowed_at"`, `value` là `"dd/mm/yyyy"`, `"yyyy-mm-dd"`, hoặc rỗng/`null`. `module_of_field(row_kind, "borrowed_at") -> Module.ASSIGNMENTS`.

- [ ] **Step 1: Write the failing tests** (HTTP qua `admin_client`, helper `_patch` chép từ `test_so_tong_edit.py`):
  - `test_edit_date_accepts_both_formats`: lượt mở của `seed["asset"]`; `"15/09/2026"` → `borrowed_at == date(2026,9,15)`; `"2026-09-14"` → `date(2026,9,14)`; có một dòng `AuditLog` table `assignments`.
  - `test_clear_date_keeps_holder`: value `""` → `borrowed_at is None`, `returned_at is None`, cùng `person_id`.
  - `@pytest.mark.parametrize("value", ["abc", "31/02/2026", "15-09-2026x", "2026/13/01"])` `test_bad_date_is_400(value)` → 400. (Review Focus 1)
  - `test_future_date_is_refused`: `today_local() + 1 ngày` → 400.
  - `test_date_cannot_overlap_previous_holder`: lượt cũ đã đóng `2026-09-01`→`2026-09-20`, lượt mở hiện tại; sửa thành `"10/09/2026"` → 400; `"20/09/2026"` → 200.
  - `test_row_without_open_assignment_refuses_date`: dòng `asset-` không ai giữ → 400; dòng `person-` → 400.
  - `test_view_only_user_cannot_edit_date(client, ...)`: người chỉ xem → 403, ngày không đổi. (Review Focus 4)

- [ ] **Step 2: Run** `venv\Scripts\pytest.exe tests\test_handover_date.py -q` — Expected: FAIL (400 "Ô này không sửa trực tiếp được").

- [ ] **Step 3: Implement**
  - `module_of_field`: `"borrowed_at"` → `Module.ASSIGNMENTS`.
  - `update_cell`, nhánh `field == "borrowed_at"`: chỉ dòng `asset` có lượt mở (dùng `assignment_service.get_active_assignment`); parse bằng hàm mới `_parse_date(value: str | None) -> dt.date | None` (thử `%d/%m/%Y` rồi `date.fromisoformat`, sai thì `ValueError("Ngày bàn giao không hợp lệ (dd/mm/yyyy).")`); từ chối ngày > `today_local()`; từ chối ngày < `returned_at` lớn nhất của các lượt đã đóng cùng máy; lưu bằng `_save(db, assignment, "assignments", "borrowed_at", ...)`.
  - `so_tong.html`: cột ngày editable khi `PERMS.assignments && row.asset_id && row.person_id` (thêm `assignments` vào `PERMS` từ router nếu chưa có); editor `'input'`; sorter đặt ô trống cuối (`sorter: 'date', sorterParams: { format: 'dd/MM/yyyy', alignEmptyValues: 'bottom' }` hoặc sorter tự viết). Ô trống hiển thị trống.

- [ ] **Step 4: Run** `venv\Scripts\pytest.exe -q`, `ruff` — PASS.

- [ ] **Step 5: Browser check** (server local trỏ DB test, không trỏ Aiven): sửa ngày, xóa trống, gõ sai thấy thông báo lỗi.

- [ ] **Step 6: Commit** `feat(so-tong): sua va xoa trong ngay ban giao`

### Task 3: Cột mật khẩu ghi rõ loại

**Files:**
- Modify: `app/services/ledger_service.py` (`_people_with_secret` → `_secret_kinds`, `build_ledger_rows`), `templates/sqladmin/so_tong.html:188`, `tests/test_so_tong_edit.py:262` (khóa `secret_set` đổi thành `secret_kind`)
- Test: `tests/test_so_tong_edit.py`

**Interfaces:**
- Produces: ledger row `"secret_kind"`: `"pc" | "email" | "both" | "none"` khi `include_secret_flag=True` và dòng có người; `None` khi không có quyền hoặc dòng không có người. Khóa `secret_set` bị bỏ.

- [ ] **Step 1: Write the failing test** `test_secret_kind_tells_pc_email_or_both`: ba người với `PersonSecret` lần lượt chỉ `pc_password_enc`, chỉ `email_password_enc`, cả hai; một người không có → `"pc"`, `"email"`, `"both"`, `"none"`. Viết lại test dòng 262: không quyền → mọi `secret_kind is None`; `"CIPHERTEXT" not in res.text`.

- [ ] **Step 2: Run** — FAIL (KeyError `secret_kind`).

- [ ] **Step 3: Implement** `_secret_kinds(db) -> dict[int, str]` chỉ select `person_id`, `pc_password_enc.is_not(None)`, `email_password_enc.is_not(None)` (không select cột mã hóa). Template: cột `secret_kind`, formatter nhãn `TEXT.secretKind = { none: L('Không có','None','なし'), pc: 'PC', email: 'Email', both: 'PC + Email' }`, `headerFilter: 'list'` với các nhãn đó, `download` dùng nhãn. Bỏ `'secret_set'` khỏi danh sách cột không mở panel (`so_tong.html:390`) và thay bằng `'secret_kind'`.

- [ ] **Step 4: Run** `pytest -q`, `ruff` — PASS. **Step 5: Commit** `feat(so-tong): cot mat khau ghi ro PC, Email`

### Task 4: Kiểu đánh dấu — service và API

**Files:**
- Create: `app/services/mark_service.py`, `tests/test_marks.py`
- Modify: `app/routers/so_tong.py`, `app/services/ledger_service.py` (`build_ledger_rows`, `_row_kind`), `app/admin.py` (`AssetTagAdmin.on_model_change`)

**Interfaces:**
- Produces (`app/services/mark_service.py`):
  - `MARK_TAG_PREFIX = "MARK-"`
  - `list_marks(db: Session) -> list[dict]` → `[{"id": int, "code": str, "name": str, "color": str, "count": int}]`, sắp theo tên; `count` là số máy còn sống đang mang.
  - `create_mark(db, name: str, color: str, user_id: int | None, ip_address: str | None) -> AssetTag`
  - `update_mark(db, tag_id: int, name: str, color: str, user_id, ip_address) -> AssetTag`
  - `delete_mark(db, tag_id: int, user_id, ip_address) -> int` (số máy bị gỡ)
  - `set_asset_mark(db, asset_id: int, tag_id: int | None, user_id, ip_address) -> None`
  - Lỗi nghiệp vụ là `ValueError` với thông báo tiếng Việt.
- Produces (router, prefix như các API hiện có `/admin/api/so-tong`): `GET /marks` (quyền xem Sổ tổng), `POST /marks` `{name, color}`, `PATCH /marks/{tag_id}` `{name, color}`, `DELETE /marks/{tag_id}`, `PUT /mark` `{asset_id, tag_id | null}`. Ghi cần `assets:change`. Trả `{"success": True, "marks": list_marks(...), "rows": ...}` (PUT `/mark` trả `rows` của máy đó như `/software`).
- Produces (ledger row): `"mark"`: `{"id", "name", "color"}` hoặc `None`. `row_kind` chỉ còn `"resigned"` hoặc `""` (bỏ luật chữ "MES").

- [ ] **Step 1: Write the failing tests** trong `tests/test_marks.py`:
  - `test_create_mark_generates_code_and_audits`: `create_mark(db, "Máy MES", "#fef9c3", ...)` → `code.startswith("MARK-")`, mã chỉ ASCII in hoa / số / `-`, ≤ 30 ký tự; tạo lần hai cùng tên (khác hoa thường) → `ValueError`; có `AuditLog`.
  - `@pytest.mark.parametrize("color", ["red", "#fff", "#12345g", "", None])` `test_bad_color_is_refused` → `ValueError`. Qua HTTP `POST` → 400. (Review Focus 3)
  - `test_asset_has_at_most_one_mark`: gắn A rồi gắn B → máy chỉ còn B; `tag_id=None` → không còn mark; nhãn `SW-` trên máy vẫn còn.
  - `test_set_asset_software_keeps_mark`: `set_asset_software(db, asset_id, [])` không gỡ mark.
  - `test_delete_mark_unlinks_assets_and_soft_deletes`: mark gắn 2 máy → `delete_mark` trả `2`, tag `is_deleted`, có `delete_reason`; tạo lại mark cùng tên sau đó được.
  - `test_ledger_row_carries_mark` và `test_mes_note_no_longer_colors_row`: máy có ghi chú "MES system PC 01" không có mark → `row_kind == ""`, `mark is None`.
  - `test_mark_name_is_returned_as_plain_text`: tên `"<img src=x onerror=alert(1)>"` lưu và trả nguyên văn trong JSON (việc chống chạy là ở frontend, Task 5).
  - `test_view_only_user_cannot_change_marks(client, ...)`: POST/PATCH/DELETE/PUT → 403; GET → 200. (Review Focus 4)
  - `test_cannot_set_mark_with_software_tag_or_deleted_tag` → 400.
  - `test_tag_admin_refuses_switching_between_mark_and_software`: `AssetTagAdmin().on_model_change({"code": "SW-X"}, <tag MARK-...>, False, DummyRequest(...))` → `ValueError`; ngược lại cũng vậy.

- [ ] **Step 2: Run** `venv\Scripts\pytest.exe tests\test_marks.py -q` — FAIL (module not found).

- [ ] **Step 3: Implement** `mark_service.py` theo Interfaces. Mã sinh từ tên: bỏ dấu tiếng Việt (`unicodedata.normalize("NFKD")`, đổi `đ`→`d`), in hoa, ký tự khác chữ / số thành `-`, cắt cho tổng ≤ 30, thêm `-2`, `-3`… nếu trùng mã còn sống; tên không có chữ cái Latin nào (vd. tiếng Nhật) thì dùng `MARK-` + số thứ tự. Tên: cắt khoảng trắng, 1–100 ký tự, duy nhất (không phân biệt hoa thường) trong các mark còn sống. Xóa: gỡ link, xóa mềm tag với `delete_reason="Xóa kiểu đánh dấu trên Sổ tổng"`. Router dùng `read_json_object`, `require_positive_int`, `optional_text` như các handler hiện có. `AssetTagAdmin.on_model_change`: khi sửa, chặn đổi mã từ `MARK-` sang khác hoặc ngược lại. Gọi `invalidate_model_count_cache` sau khi ghi `asset_tags` nếu các router khác đang làm vậy.

- [ ] **Step 4: Run** `pytest -q`, `ruff` — PASS. **Step 5: Commit** `feat(so-tong): kieu danh dau mau cho may`

### Task 5: Kiểu đánh dấu — giao diện Sổ tổng

**Files:**
- Modify: `templates/sqladmin/so_tong.html`, `app/routers/so_tong.py` (truyền `marks` ban đầu vào template nếu tiện), `tests/test_mobile_layout.py` hoặc `tests/test_so_tong.py`

**Interfaces:**
- Consumes: API và dữ liệu `mark` từ Task 4.

- [ ] **Step 1: Write the failing test** `test_page_has_mark_legend_and_manager(admin_client, ...)`: HTML trang `/admin/so-tong` chứa `id="stLegend"`, `id="stMarkManager"`, và chữ `renderLegend`; với người chỉ xem: có `stLegend` nhưng không có nút mở `stMarkManager`.

- [ ] **Step 2: Run** — FAIL.

- [ ] **Step 3: Implement**
  - **Chú giải** `#stLegend` phía trên bảng: mỗi mark là một nút có ô màu, tên (gán bằng `textContent`), số máy; bấm thì lọc bảng theo `mark.id` (kết hợp được với chip trạng thái), bấm lại bỏ lọc. Có nút "Quản lý màu" (chỉ khi `PERMS.assets`).
  - **Hộp quản lý** `#stMarkManager` (modal Bootstrap có sẵn trong layout): danh sách mark với ô tên, `<input type="color">`, nút lưu, nút xóa; xóa mark đang dùng thì `confirm` kiểu tự dựng trong modal (không dùng `window.confirm`) nêu số máy sẽ mất màu; dòng thêm mới.
  - **Cột "Đánh dấu"** (`field: 'mark'`): hiện ô màu + tên; editor `list` với các mark + "Không đánh dấu", chỉ dòng có `asset_id` và `PERMS.assets`; gọi `PUT /admin/api/so-tong/mark`; `headerFilter` theo tên; xuất Excel dùng tên.
  - **Màu dòng** trong `rowFormatter` và thẻ điện thoại: nền là `mark.color`; chữ tối hoặc sáng theo độ sáng màu (công thức luminance); dòng `resigned` không có mark vẫn xám; bỏ CSS `.st-mes`.
  - Sau mỗi thay đổi mark: cập nhật lại chú giải và các dòng bị ảnh hưởng (tải lại dữ liệu bảng là chấp nhận được).
  - Mọi tên mark đưa vào DOM bằng `textContent` (Review Focus 3).

- [ ] **Step 4: Run** `pytest -q`, `ruff` — PASS.

- [ ] **Step 5: Browser check** (DB local test): tạo mark có tên chứa HTML, đổi màu, gắn cho máy, lọc bằng chú giải, xóa mark đang dùng, xem trên khổ điện thoại (375px), kiểm tra không có lỗi trong console.

- [ ] **Step 6: Commit** `feat(so-tong): chu giai va to mau dong theo danh dau`

### Task 6: Script dọn dữ liệu đợt nhập Excel

**Files:**
- Create: `scripts/cleanup_excel_import.py`, `tests/test_cleanup_excel_import.py`

**Interfaces:**
- Consumes: `mark_service.create_mark`, `mark_service.set_asset_mark` (Task 4); `borrowed_at` NULL (Task 1).
- Produces: `plan_and_apply(db: Session, actor_id: int) -> CleanupReport` (không commit; người gọi commit hoặc rollback). `CleanupReport` là dataclass: `dates_cleared: int`, `assignment_notes_cleared: int`, `asset_notes_cleared: int`, `asset_notes_shortened: list[tuple[str, str]]` (pc_name, ghi chú mới), `mes_marked: list[str]`, `skipped: list[str]` (lý do), `foreign_tags: list[str]`. CLI: `python -m scripts.cleanup_excel_import [--apply]`, mặc định chạy thử và rollback; in báo cáo; từ chối chạy nếu không tìm thấy user `manhhung`.

Luật (nguyên văn từ spec, khớp chính xác, bỏ qua mọi thứ khác và ghi vào `skipped`):

| Đối tượng | Khớp | Làm |
|---|---|---|
| Lượt mở | note bắt đầu `"Ngày bàn giao tạm ("` và `borrowed_at` ∈ {2026-10-16, 2026-11-02} | `borrowed_at = NULL`, note = NULL |
| Lượt mở | note bắt đầu `"Ngày bàn giao tạm ("` nhưng ngày khác | chỉ xóa note, giữ ngày (người dùng đã sửa) |
| Lượt | note bắt đầu `"Purchasing's PC - "` hoặc `"HR's PC - "` và chứa `"Ngày bàn giao tạm"` | xử lý ngày như trên, note = NULL; máy HR nhận ghi chú máy "Máy dùng chung Nhân sự - Phạm Huy Chương quản lý" |
| Máy | note == `"Đã bàn giao từ dữ liệu file Excel (ngày bàn giao tạm)."` | note = NULL |
| Máy | note `"Người dùng theo file Excel: MES system PC NN. Chưa bàn giao trong hệ thống."` | gắn mark "Máy MES", note = `"MES system PC NN"` |
| Máy | note bắt đầu `"Purchasing's PC - máy dùng chung"` | note = "Máy dùng chung Mua hàng - Phạm Cù Phương Thảo quản lý" |
| Máy | note `"Người dùng theo file Excel: General Affairs (Ms Tiên quản lý ). …"` | "Máy dùng chung General Affairs - Ms Tiên quản lý" |
| Máy | `"… Financial Department (Ms Thoan quản lý). …"` | "Máy dùng chung phòng Tài chính - Ms Thoan quản lý" |
| Máy | `"… QA (Sakurai quản lý). …"` | "Máy dùng chung QA - Sakurai quản lý" |
| Máy | `"Người dùng cũ theo file Excel: <Tên> (mã NV <Mã>) - đã nghỉ việc / về nước. …"` | "Người dùng cũ: <Tên> (<Mã>), đã nghỉ" |

Tạo mark "Máy MES" `#fef9c3` và "Không cài Zscaler" `#fecaca` nếu chưa có (tìm theo tên, không phân biệt hoa thường). Tag còn sống không phải `SW-`/`MARK-` → liệt kê trong `foreign_tags`, không đụng. Mỗi thay đổi ghi audit với `extra={"source": "cleanup-excel-import"}`.

- [ ] **Step 1: Write the failing tests** dựng dữ liệu mẫu với đúng các chuỗi trong bảng (lấy nguyên văn từ bản khôi phục local của backup; xem Step 4):
  - `test_cleanup_applies_every_rule`: kiểm từng hàng của bảng trên.
  - `test_cleanup_leaves_user_data_alone`: note `"my ntoe"`, lượt mở ngày `2026-09-20` không note, note tạm nhưng ngày `2026-10-20` → giữ ngày; báo trong `skipped`.
  - `test_cleanup_is_idempotent`: chạy hai lần, lần hai mọi bộ đếm = 0, không tạo mark trùng. (Review Focus 5)
  - `test_cleanup_reports_foreign_tags`: tag `ZSCALER` còn sống → nằm trong `foreign_tags`, không bị sửa.

- [ ] **Step 2: Run** — FAIL. **Step 3: Implement** theo bảng.

- [ ] **Step 4: Dry run trên bản sao local**: khôi phục `C:\Users\hungm\itam-backups\aiven-before-0005-*.dump` (mới nhất) vào DB local `itam_test_cleanup` bằng `pg_restore` (`C:\Program Files\PostgreSQL\18\bin`), đặt `ITAM_DATABASE_URL` tới DB đó, `alembic upgrade head`, chạy `python -m scripts.cleanup_excel_import --apply`. Expected: `dates_cleared == 51`, `assignment_notes_cleared == 53`, `asset_notes_cleared == 49`, `len(mes_marked) == 8`, 7 ghi chú rút gọn trên máy + 1 máy HR, `"my ntoe"` còn nguyên. Xóa DB tạm sau khi xong.

- [ ] **Step 5: Run** `pytest -q`, `ruff` — PASS. **Step 6: Commit** `feat(scripts): don ghi chu va ngay tam tu dot nhap Excel`

### Task 7: Tài liệu bàn giao

**Files:** Modify `HANDOVER.md`, `docs/database.dbml` (note `asset_tags.code`: `MARK-` là kiểu đánh dấu màu).

- [ ] **Step 1:** Ghi vào `HANDOVER.md`: tính năng mới, migration `0006`, script dọn dữ liệu và thứ tự lên production (sao lưu → `0006` → merge `main` vào `master` và chờ Render deploy → script `--apply`), nhắc Render deploy từ `master`.
- [ ] **Step 2: Commit** `docs: cap nhat ban giao cho danh dau mau va ngay ban giao`

---

## Đưa lên production (không phải task cho agent, cần người dùng cho phép từng bước)

1. Sao lưu Aiven (`pg_dump`, như lần 02/11).
2. Người dùng tự chạy `! venv/Scripts/python.exe -m alembic upgrade head` (chỉ đổi cột thành cho phép NULL, code cũ vẫn chạy).
3. Push `main`, merge `main` vào `master`, chờ Render "Deploy live" đúng commit mới.
4. Chạy thử `python -m scripts.cleanup_excel_import` trên Aiven (rollback), cho người dùng xem báo cáo, rồi chạy `--apply` khi được phép.
5. Mở Sổ tổng trên trang thật kiểm tra.
