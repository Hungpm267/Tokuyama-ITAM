# Phase 2: Assets & Assignments Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Triển khai hoàn chỉnh module Quản lý Tài sản và Bàn giao Mượn–trả (Assets & Assignments) từ Service → Router → Template theo chuẩn GEMINI.md và BRD.md.

**Architecture:** Xây dựng tầng Service nghiệp vụ (`app/services/asset_service.py`, `app/services/assignment_service.py`) đóng gói toàn bộ logic trạng thái, kiểm tra ràng buộc, và audit logs; router mỏng (`app/routers/assets.py`) xử lý request/response và phân quyền; giao diện SQLAdmin tích hợp nút Quick Assign / Quick Return và timeline lịch sử.

**Tech Stack:** FastAPI, SQLAlchemy 2.x, PostgreSQL, Jinja2, SQLAdmin, Pytest.

**Spec:** `docs/superpowers/specs/2026-10-08-phase2-assets-assignments-design.md`

## Global Constraints

- Tuân thủ bất biến GEMINI.md: không sửa file `app/models.py`, không gọi `create_all()`.
- Lịch sử bàn giao không bao giờ bị xoá, chỉ đóng bằng `returned_at`.
- Ràng buộc partial unique index: mỗi máy chỉ có tối đa 1 người giữ tại 1 thời điểm (`returned_at IS NULL`).
- Ghi audit log đầy đủ cho mọi thao tác CREATE, UPDATE, DELETE.
- Code Python 3.12, type hints đầy đủ, `from __future__ import annotations`.

---

### Task 1: Asset Service (`app/services/asset_service.py`)

**Files:**
- Create: `app/services/__init__.py`
- Create: `app/services/asset_service.py`
- Test: `tests/test_phase2_assets.py`

**Interfaces:**
- `create_asset(db: Session, data: dict, user_id: int | None, ip_address: str | None) -> Asset`
- `update_asset(db: Session, asset_id: int, data: dict, user_id: int | None, ip_address: str | None) -> Asset`
- `soft_delete_asset(db: Session, asset_id: int, delete_reason: str, user_id: int | None, ip_address: str | None) -> Asset`
- `set_asset_tags(db: Session, asset_id: int, tag_ids: list[int], user_id: int | None, ip_address: str | None) -> None`
- `get_asset(db: Session, asset_id: int) -> Asset | None`

- [x] **Step 1: Write failing test in `tests/test_phase2_assets.py`**
- [x] **Step 2: Run pytest to verify test fails**
- [x] **Step 3: Implement `app/services/asset_service.py`**
- [x] **Step 4: Run pytest to verify test passes**
- [x] **Step 5: Commit changes**

---

### Task 2: Assignment Service (`app/services/assignment_service.py`)

**Files:**
- Create: `app/services/assignment_service.py`
- Test: `tests/test_phase2_assignments.py`

**Interfaces:**
- `assign_asset(db: Session, asset_id: int, person_id: int, borrowed_at: dt.date, note: str | None, user_id: int | None, ip_address: str | None) -> Assignment`
- `return_asset(db: Session, asset_id: int, returned_at: dt.date, return_status: AssetStatus, note: str | None, user_id: int | None, ip_address: str | None) -> Assignment`
- `get_active_assignment(db: Session, asset_id: int) -> Assignment | None`
- `get_asset_assignment_history(db: Session, asset_id: int) -> list[Assignment]`

- [x] **Step 1: Write failing test in `tests/test_phase2_assignments.py`**
- [x] **Step 2: Run pytest to verify test fails**
- [x] **Step 3: Implement `app/services/assignment_service.py`**
- [x] **Step 4: Run pytest to verify test passes**
- [x] **Step 5: Commit changes**

---

### Task 3: Asset & Assignment Router (`app/routers/assets.py`)

**Files:**
- Create: `app/routers/assets.py`
- Modify: `app/main.py`
- Test: `tests/test_phase2_router.py`

**Interfaces:**
- `POST /admin/assets/{asset_id}/assign`: Bàn giao máy cho nhân viên.
- `POST /admin/assets/{asset_id}/return`: Thu hồi máy về kho / sửa chữa.
- `GET /admin/assets/{asset_id}/history`: Lấy lịch sử bàn giao của máy.
- `GET /admin/api/persons/search`: Tìm kiếm nhân viên để autocomplete khi bàn giao.

- [x] **Step 1: Write failing router test in `tests/test_phase2_router.py`**
- [x] **Step 2: Run pytest to verify test fails**
- [x] **Step 3: Implement `app/routers/assets.py` và đăng ký router trong `app/main.py`**
- [x] **Step 4: Run pytest to verify test passes**
- [x] **Step 5: Commit changes**

---

### Task 4: UI Templates & SQLAdmin Integration

**Files:**
- Modify: `app/admin.py`
- Create/Modify: `templates/sqladmin/asset_actions_modal.html`
- Modify: `templates/sqladmin/details.html` (thêm block lịch sử bàn giao máy)

- [x] **Step 1: Bổ sung các formatters và action buttons trong `AssetAdmin` (Nút Bàn giao máy khi `IN_STOCK`, Nút Thu hồi máy khi `IN_USE`)**
- [x] **Step 2: Thêm Modal bàn giao và thu hồi trực quan có CSRF token**
- [x] **Step 3: Bổ sung timeline hiển thị lịch sử bàn giao trong trang chi tiết thiết bị**
- [x] **Step 4: Kiểm tra giao diện và đảm bảo CSS chuẩn với thiết kế chung**
- [x] **Step 5: Commit changes**

---

### Task 5: Toàn bộ kiểm thử hồi quy & hoàn tất Giai đoạn 2

**Files:**
- Run all test suites: `pytest`

- [x] **Step 1: Chạy toàn bộ pytest kiểm tra 101 test cũ và tất cả test mới của Giai đoạn 2**
- [x] **Step 2: Đảm bảo 100% test xanh (PASSED)**
- [x] **Step 3: Kiểm tra ruff check code cleanliness**
- [x] **Step 4: Commit và chuẩn bị sẵn sàng cho người dùng test thử**
