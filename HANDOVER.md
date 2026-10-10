# BÀN GIAO DỰ ÁN ITAM TOKUYAMA VIETNAM (HANDOVER FOR AI AGENT)

> **Dành cho Model AI tiếp nhận phiên làm việc (Gemini / Astra / Cursor / Claude)**  
> Hãy đọc kỹ tài liệu này kết hợp cùng `GEMINI.md` trước khi viết bất kỳ dòng code nào.

---

## 1. TỔNG QUAN DỰ ÁN & BỐI CẢNH

- **Tên dự án**: Web App Quản lý Tài sản IT nội bộ (**ITAM Tokuyama Vietnam**).
- **Mục tiêu cốt lõi**: Thay thế toàn bộ hệ thống file Excel phân tán, giải quyết các painpoint nhức nhối: mất dấu thiết bị, trùng lặp serial, thất thoát bản quyền phần mềm, mượn thẻ không trả, rò rỉ mật khẩu máy tính của nhân viên.
- **Người dùng thực tế**: 5 người
  - 1 Chuyên viên IT (Vai trò: `ADMIN`)
  - 1 Trưởng phòng GA (Vai trò: `GA_MANAGER`)
  - 3 Giám đốc người Nhật (Vai trò: `EXECUTIVE`, giao diện tiếng Nhật song ngữ)
- **Tài liệu nghiệp vụ gốc**: `docs/BRD.md` (Business Requirements Document).
- **Tech Stack**:
  - **Backend**: FastAPI + SQLAlchemy 2.0 (`Mapped[...]`) + PostgreSQL + Alembic
  - **Quản trị & UI**: SQLAdmin (tùy biến giao diện phong cách Swiss Enterprise) + Jinja2 + Tabler/Bootstrap 5
  - **Bảo mật**: Argon2id (mật khẩu user hệ thống), AES-256-GCM + AAD (Kho mật khẩu nhân viên `person_secrets`)
  - **Kiểm thử**: Pytest (167 test cases, 100% pass)
  - **Linter**: Ruff

---

## 2. BẢNG TRẠNG THÁI TIẾN ĐỘ THỰC TẾ (PROGRESS STATUS)

Toàn bộ các giai đoạn nghiệp vụ cốt lõi đã được hoàn thiện và kiểm thử tự động toàn diện:

| Giai đoạn | Nội dung | Trạng thái | Đánh giá / Ghi chú |
|---|---|:---:|---|
| **Nền tảng** | Schema 23 bảng đóng băng (`app/models.py`), migration Alembic, mã hóa AES-256-GCM (`app/core/crypto.py`), cổng xem mật khẩu RevealGate (`app/core/reveal.py`), DB triggers chống sửa/xóa audit log. | ✅ **100% ĐẠT** | 20 test ràng buộc DB xanh |
| **Giai đoạn 1** | Bảo mật Argon2id, RBAC 3 vai trò (`ADMIN`, `GA_MANAGER`, `EXECUTIVE`), ghi Audit Log tự động loại bỏ trường nhạy cảm, SQLAdmin Portal, Ma trận phân quyền động (`/admin/role-permission-matrix`). | ✅ **100% ĐẠT** | Default-deny; phân quyền cấp router |
| **Giai đoạn 2** | **Tài sản Phần cứng & Vòng đời Mượn - Trả**: Service gán/thu hồi thiết bị, lịch sử mượn, modal thao tác nhanh, chống trùng lặp thời gian, kiểm soát trạng thái máy (`IN_STOCK`, `IN_USE`, `REPAIR`). | ✅ **100% ĐẠT** | Đã chặn ngày tương lai; sửa popup thu hồi |
| **Giai đoạn 3** | **Quản lý Nhân sự & Kho Mật khẩu (FR-06)**: CRUD nhân sự, chặn xóa mềm khi đang giữ máy/thẻ/bản quyền, màn hình Password Vault (`/admin/person-secret/list`) với xác thực mật khẩu 2 phút, tự ẩn sau 60s, lockout 15 phút nếu sai 5 lần. | ✅ **100% ĐẠT** | Tuyệt đối tuân thủ bảo mật |
| **Giai đoạn 4** | **Bản quyền, Thẻ ra vào, Hợp đồng Mua sắm**: Quản lý seat license (tính động từ assignments, cấm gán vượt số lượng), Sổ mượn trả thẻ (hỗ trợ cả nhân viên & nhà thầu ngoài), Đếm số lượng nhận hàng từ `assets.contract_line_id` (không cột gõ tay), Nhập kho theo lô (Batch Receive). | ✅ **100% ĐẠT** | Đúng quy tắc Rule 7 & Rule 8 |
| **Giai đoạn 5** | **Tính năng mở rộng & Giao diện Doanh nghiệp**: Danh bạ điện thoại nội bộ (Phone List), Tìm kiếm toàn cầu (Global Search với phím tắt `Ctrl + K`), Đa ngôn ngữ trilingual (Việt - Anh - Nhật), Thùng rác phục hồi dữ liệu (`/admin/trash`), Dashboard phong cách Swiss Executive với Smart Alerts. | ✅ **100% ĐẠT** | UI đồng bộ, phông chữ Inter & JetBrains Mono |
| **Độ phủ Test** | Bộ test tự động toàn diện gồm 167 bài test (`tests/`). | ✅ **167/167 PASS** | Chạy `venv\Scripts\pytest.exe -v` |

---

## 3. CÁC THAY ĐỔI MỚI NHẤT VỪA THỰC HIỆN (LOCAL WORKING TREE)

> [!IMPORTANT]
> **Hiện tại các thay đổi này đang nằm ở Local (chưa commit/push theo yêu cầu của User để kiểm tra trên máy trước).**

1. **Chặn cấp phát / thu hồi ngày tương lai**:
   - `app/services/assignment_service.py`: Cả `assign_asset` và `return_asset` đều kiểm tra `date <= dt.date.today()`.
   - `app/admin.py`: `AssignmentAdmin.on_model_change` validate và thông báo lỗi đa ngôn ngữ nếu chọn ngày tương lai.
   - `app/routers/assets.py`: Endpoint `/admin/assets/{id}/assign` và `/admin/assets/{id}/return` validate và trả lỗi 400 rõ ràng.
   - `templates/sqladmin/asset_actions_modal.html`: Ô chọn ngày có `max="YYYY-MM-DD"`, tự động chặn và cảnh báo nếu người dùng nhập tay ngày tương lai.
2. **Kích hoạt nút Thu hồi trên tab Lịch sử Cấp phát**:
   - `templates/sqladmin/list.html` và `details.html`: Bổ sung `asset_actions_modal.html` cho identity `assignment`.
3. **Sửa lỗi không bấm được [X] hoặc [Hủy bỏ] để thoát modal**:
   - `templates/sqladmin/asset_actions_modal.html`: Viết lại cơ chế đóng modal 3 lớp an toàn (`closeAssetModal`) hỗ trợ Bootstrap 5, Bootstrap 4 / jQuery, và fallback DOM. Hỗ trợ phím `Escape` và click ra ngoài backdrop.
4. **Bổ sung test tự động**: Đã thêm 5 test case mới vào `tests/test_phase1.py`, `tests/test_phase2_assignments.py`, `tests/test_phase2_router.py`.

---

## 4. CẤU TRÚC CODEBASE & NGUỒN SỰ THẬT

```
toku-app/
│
├── app/
│   ├── models.py              # 23 bảng SQLAlchemy. [SCHEMA ĐÃ ĐÓNG BĂNG - KHÔNG SỬA]
│   ├── enums.py               # ENUM native PostgreSQL + DEFAULT_ROLE_PERMISSIONS
│   ├── db.py                  # Base, session maker, mixin SoftDelete, Auditable
│   ├── config.py              # Settings đọc biến môi trường
│   ├── admin.py               # SQLAdmin ModelViews, formatters, on_model_change validation
│   ├── main.py                # FastAPI app entrypoint, cấu hình middleware, session, static
│   ├── core/
│   │   ├── crypto.py          # AES-256-GCM mã hóa person_secrets với AAD
│   │   ├── reveal.py          # RevealGate: cấp token 2 phút xem mật khẩu, lockout 5 lần
│   │   ├── security.py        # Băm mật khẩu Argon2id, tạo session token
│   │   ├── permissions.py     # Dependency kiểm tra RBAC (default-deny)
│   │   ├── audit.py           # Ghi audit log, sanitize REDACTED_FIELDS
│   │   └── i18n.py            # Từ điển song ngữ 3 thứ tiếng (VI, EN, JA)
│   ├── services/              # Tầng nghiệp vụ cốt lõi (asset, assignment, license, card, contract...)
│   └── routers/               # Endpoint FastAPI mỏng (auth, assets, trash, role_matrix, batch_receive...)
│
├── templates/sqladmin/        # Giao diện Jinja2 tùy biến
│   ├── layout.html            # Top utility bar (56px), Swiss Sidebar, Instant prefetch
│   ├── index.html             # Dashboard tổng quan phong cách Swiss Executive
│   ├── list.html              # Danh sách bản ghi, phân trang, bộ lọc, modal include
│   ├── details.html           # Chi tiết bản ghi, bảng con quan hệ
│   ├── asset_actions_modal.html # Modal bàn giao & thu hồi máy
│   └── person_secrets.html    # Giao diện bảo mật xem mật khẩu nhân viên
│
├── tests/                     # 167 bài test tự động bao quát toàn bộ hệ thống
├── docs/                      # Tài liệu phân tích yêu cầu nghiệp vụ BRD.md
├── GEMINI.md                  # Bản quy ước bất biến tối thượng của dự án
└── HANDOVER.md                # File này (hướng dẫn bàn giao cho AI Agent)
```

---

## 5. NGUYÊN TẮC BẤT BIẾN TỐI THƯỢNG (AI TUYỆT ĐỐI TUÂN THỦ)

1. **Schema đã đóng băng**: `app/models.py` là nguồn sự thật duy nhất. Tuyệt đối không thêm/sửa cột hay bảng bằng SQL tay, không gọi `Base.metadata.create_all()`. Mọi thay đổi bắt buộc qua Alembic.
2. **Bộ test là hợp đồng**: `pytest` phải xanh 100% (hiện tại là 167/167 pass). Nếu sửa code làm đỏ test, cái sai là code mới. Tuyệt đối không sửa hay xóa test để cho qua.
3. **Mật khẩu nhân viên là tối mật (FR-06)**:
   - Nằm ở bảng riêng `person_secrets`, mã hóa AES-256-GCM với AAD.
   - CẤM trả plaintext mật khẩu ở bất kỳ endpoint danh sách, template, CSV export, hay log nào.
   - Đi qua cổng `RevealGate`: Chỉ Admin có quyền, phải xác thực lại mật khẩu đăng nhập của chính mình, token sống 2 phút, sai 5 lần khóa 15 phút, tự ẩn sau 60 giây, mọi lần xem đều ghi audit log `REVEAL`.
4. **Kiểm tra xóa mềm**: Các bảng nghiệp vụ mặc định lọc `is_deleted = false`. Xóa là xoá mềm kèm `delete_reason`. Các bảng lịch sử (`assignments`, `license_assignments`, `card_loans`, `audit_logs`) KHÔNG xóa, chỉ đóng bằng ngày kết thúc.
5. **Quy tắc đếm hợp đồng (Rule 8)**: Không thêm cột `delivered_qty` hay `remaining_qty` thủ công vào `contract_lines`. Số lượng đã nhận được `COUNT` động từ `assets.contract_line_id`.
6. **Quy tắc làm việc với User**:
   - **Tuyệt đối KHÔNG tự ý `git push` lên GitHub** trừ khi User ra lệnh rõ ràng. User luôn kiểm tra trên máy local trước.
   - Luôn chạy `pytest` và `ruff check .` để xác minh chất lượng trước khi tuyên bố hoàn thành.

---

## 6. LỆNH VẬN HÀNH & KIỂM THỬ TRÊN MÁY LOCAL (WINDOWS)

Môi trường chạy bằng PowerShell trên Windows:

```powershell
# 1. Chạy toàn bộ 167 bài kiểm thử (Phải pass 100%)
venv\Scripts\pytest.exe -v

# 2. Kiểm tra định dạng và chất lượng code bằng Ruff
venv\Scripts\ruff.exe check .

# 3. Khởi chạy Web Server local
venv\Scripts\uvicorn.exe app.main:app --reload --port 8000
```

- **Đường dẫn quản trị web**: `http://localhost:8000/admin`
- **Tài khoản Admin mặc định**: `it.admin` / mật khẩu khởi tạo trong seed hoặc database local.

---

## 7. CÔNG VIỆC TIẾP THEO CẦN LÀM (NEXT STEPS)

Khi tiếp nhận phiên làm việc, Model AI cần:
1. Hỏi người dùng xem đã test thử 3 tính năng (chặn ngày tương lai, nút thu hồi, đóng modal) trên trình duyệt local hay chưa.
2. Nếu người dùng hài lòng: Tiến hành commit sạch với thông điệp rõ ràng theo định dạng Conventional Commits (ví dụ: `fix(asset): chặn cấp phát ngày tương lai và sửa lỗi popup thu hồi`).
3. Nếu người dùng muốn chuyển sang giai đoạn tiếp theo (như hoàn thiện seed dữ liệu thực tế từ Excel cũ, cấu hình database production online, hoặc deploy lên cloud Docker): Thực hiện theo đúng chỉ dẫn của User mà không phá vỡ bất kỳ bất biến nào.
