# Thiết Kế Chi Tiết Giai Đoạn 2: Quản Lý Tài Sản & Bàn Giao Mượn-Trả (Assets & Assignments)

**Ngày lập:** 08/10/2026  
**Dự án:** IT Asset Management (ITAM) - Tokuyama Vietnam  
**Mục tiêu:** Xây dựng module nghiệp vụ lõi đầu tiên xuyên suốt Service → Router → Template theo đúng bất biến GEMINI.md và BRD.md.

---

## 1. Yêu Cầu Nghiệp Vụ (BRD FR-07, FR-08, FR-09, FR-10)

1. **FR-07 (Tài sản):** Thêm, sửa, xoá mềm tài sản IT; lưu `asset_code`, `vendor_code`, `model`, `form_factor`, `serial`, `hwid`, `mac_ethernet`, `mac_wifi`, `category_id`, `contract_line_id`.
2. **FR-08 (Nhãn động):** Gắn/gỡ nhãn động (`AssetTag`: Zscaler, MES...) qua bảng nối `asset_tag_links`, không thêm cột cứng vào bảng.
3. **FR-09 (Vòng đời trạng thái):** Quản lý trạng thái: Lưu kho (`IN_STOCK`), Đang sử dụng (`IN_USE`), Sửa chữa (`REPAIR`), Thanh lý (`DISPOSED`), Mất (`LOST`).
4. **FR-10 (Bàn giao & Thu hồi):**
   - Bàn giao thiết bị cho nhân viên: tự động chuyển trạng thái sang `IN_USE`. Chặn bàn giao nếu máy đang có người giữ hoặc máy không ở trạng thái sẵn sàng.
   - Thu hồi thiết bị: đóng bản ghi bàn giao bằng `returned_at` (bắt buộc $\ge$ `borrowed_at`). Chuyển trạng thái máy về `IN_STOCK` (hoặc `REPAIR`).
   - Lịch sử bất biến: không xoá bản ghi `assignments`, chỉ đóng bằng `returned_at`.
   - Chặn xoá mềm tài sản nếu đang có người mượn.
   - Ghi nhận `audit_logs` cho mọi thao tác.

---

## 2. Thiết Kế Kiến Trúc & Cấu Trúc File

### 2.1 Tầng Dịch Vụ Nghiệp Vụ (`app/services/`)
- `app/services/asset_service.py`:
  - `create_asset(db, data, user_id)`: Tạo mới tài sản, kiểm tra trùng lặp mã/serial, ghi audit log `CREATE`.
  - `update_asset(db, asset_id, data, user_id)`: Cập nhật thông tin, ghi audit log `UPDATE` kèm before-after.
  - `soft_delete_asset(db, asset_id, delete_reason, user_id)`: Xóa mềm với lý do, chặn xóa nếu đang có `assignment` mở.
  - `set_asset_tags(db, asset_id, tag_ids, user_id)`: Gán danh sách nhãn.
  - `get_asset(db, asset_id)`: Lấy chi tiết tài sản kèm quan hệ.
- `app/services/assignment_service.py`:
  - `assign_asset(db, asset_id, person_id, borrowed_at, note, user_id)`: Bàn giao máy, cập nhật `asset.status = IN_USE`, ghi audit log.
  - `return_asset(db, asset_id, returned_at, return_status, note, user_id)`: Thu hồi máy, đóng `returned_at`, chuyển máy về kho hoặc sửa chữa, ghi audit log.
  - `get_active_assignment(db, asset_id)`: Lấy bản ghi bàn giao đang mở.
  - `get_asset_assignment_history(db, asset_id)`: Lấy lịch sử mượn trả theo thứ tự thời gian.

### 2.2 Tầng Điều Hướng & API (`app/routers/assets.py`)
- `POST /admin/assets/{asset_id}/assign`: Endpoint API nhận yêu cầu bàn giao máy cho nhân viên.
- `POST /admin/assets/{asset_id}/return`: Endpoint API nhận yêu cầu thu hồi máy về kho.
- `GET /admin/assets/{asset_id}/history`: Endpoint trả về lịch sử bàn giao dạng JSON/HTML.
- Bảo vệ CSRF và kiểm tra quyền RBAC: `has_permission(db, user, Module.ASSETS, PermissionAction.CHANGE)`.

### 2.3 Tầng Giao Diện (`templates/sqladmin/`)
- Tích hợp nút thao tác nhanh trên giao diện SQLAdmin:
  - Máy ở kho (`IN_STOCK`): nút "Bàn giao" mở Modal bàn giao.
  - Máy đang dùng (`IN_USE`): nút "Thu hồi" mở Modal thu hồi kèm thông tin người đang giữ.
- Trang chi tiết tài sản (`details.html`): Bổ sung card "Lịch sử bàn giao thiết bị" dạng timeline trực quan.

---

## 3. Kế Hoạch Kiểm Thử (`tests/test_phase2_assets_assignments.py`)
- Kiểm thử bàn giao thành công & trạng thái máy chuyển sang `IN_USE`.
- Kiểm thử chặn bàn giao đúp trên cùng một thiết bị.
- Kiểm thử thu hồi thành công & trạng thái máy chuyển sang `IN_STOCK`/`REPAIR`.
- Kiểm thử kiểm tra logic ngày trả trước ngày mượn.
- Kiểm thử chặn xoá mềm thiết bị khi đang có người giữ.
- Kiểm thử ghi nhận audit log đầy đủ.
