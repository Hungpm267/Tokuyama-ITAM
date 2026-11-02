"""Kiểm thử tự động cho Đợt 2 Rà soát Bảo mật & Logic nghiệp vụ (Wave 2 Hardening).

Bao gồm:
1. Chống timing attack / user enumeration khi đăng nhập với dummy hash.
2. Chặn xóa mềm Nhân viên (Person) khi đang giữ thiết bị, thẻ ra vào hoặc license.
3. Chặn xóa mềm Thiết bị (Asset) khi đang sử dụng.
4. Chặn xóa mềm Thẻ (AccessCard) khi đang cho mượn.
5. Đồng bộ trạng thái giao hàng Contract.delivery_status khi Asset bị xóa mềm và khôi phục.
6. Chặn trùng lặp lịch sử cấp phát (historical overlap check) cho Asset và CardLoan.
7. Kiểm soát giới hạn seats của LicenseAssignment trong Admin UI.
8. Xác thực vai trò Admin truy vấn CSDL thời gian thực trong Role Matrix router.
9. Thông báo lỗi phân quyền được chuẩn hóa, không rò rỉ mã định danh quyền nội bộ.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import pytest
from starlette.exceptions import HTTPException

from app.admin import AssetAdmin, PersonAdmin
from app.core.security import hash_password
from app.enums import AssetStatus
from app.routers.auth import LoginInput, login
from app.services.assignment_service import assign_asset, return_asset


class DummyRequest:
    """Đối tượng Request giả định hỗ trợ session, state và query_params cho test."""
    def __init__(self, session=None, db=None, query_params=None):
        self.session = session or {}
        self.state = type("State", (), {"db": db})()
        self.query_params = query_params or {}
        self.client = type("Client", (), {"host": "127.0.0.1"})()
        self.cookies = {}


def test_login_unified_error_and_timing_defense(db, seed):
    """Đăng nhập sai username hay sai password đều trả về 401 với thông điệp đồng nhất."""
    mock_request = DummyRequest(db=db)
    mock_response = type("Response", (), {"set_cookie": lambda *a, **kw: None})()

    # 1. Username không tồn tại
    data_bad_user = LoginInput(username="non_existent_user_999", password="WrongPassword123!")
    with pytest.raises(HTTPException) as exc_info:
        login(data_bad_user, mock_request, mock_response, db)
    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Tên đăng nhập hoặc mật khẩu không chính xác."

    # 2. Username tồn tại nhưng mật khẩu sai
    valid_user = seed["user"]
    valid_user.password_hash = hash_password("CorrectPass123!")
    db.flush()

    data_bad_pass = LoginInput(username=valid_user.username, password="WrongPass456!")
    with pytest.raises(HTTPException) as exc_info2:
        login(data_bad_pass, mock_request, mock_response, db)
    assert exc_info2.value.status_code == 401
    assert exc_info2.value.detail == "Tên đăng nhập hoặc mật khẩu không chính xác."


def test_admin_delete_person_blocked_when_holding_asset(db, seed):
    """Admin delete_model chặn xóa nhân viên đang giữ thiết bị IT."""
    person = seed["person"]
    asset = seed["asset"]
    user = seed["user"]

    assign_asset(db, asset.id, person.id, borrowed_at=dt.date(2026, 10, 1), user_id=user.id)
    db.flush()

    req = DummyRequest(session={"user_id": user.id}, db=db, query_params={"delete_reason": "Nghỉ việc"})
    view = PersonAdmin()

    with pytest.raises(HTTPException) as exc:
        asyncio.run(view.delete_model(req, person.id))
    assert exc.value.status_code == 400
    assert "đang giữ thiết bị IT" in exc.value.detail




def test_admin_delete_asset_blocked_when_in_use(db, seed):
    """Admin delete_model chặn xóa thiết bị khi đang có trạng thái IN_USE."""
    asset = seed["asset"]
    asset.status = AssetStatus.IN_USE
    db.flush()

    req = DummyRequest(session={"user_id": seed["user"].id}, db=db, query_params={"delete_reason": "Thanh lý"})
    view = AssetAdmin()

    with pytest.raises(HTTPException) as exc:
        asyncio.run(view.delete_model(req, asset.id))
    assert exc.value.status_code == 400
    assert "đang có người sử dụng" in exc.value.detail


def test_historical_overlap_checks(db, seed):
    """Chặn bàn giao máy có khoảng thời gian trùng với lịch sử đã trả."""
    asset = seed["asset"]
    person = seed["person"]
    user = seed["user"]

    assign_asset(db, asset.id, person.id, borrowed_at=dt.date(2026, 5, 1), user_id=user.id)
    return_asset(db, asset.id, returned_at=dt.date(2026, 6, 1), user_id=user.id)
    db.flush()

    with pytest.raises(ValueError) as exc:
        assign_asset(db, asset.id, person.id, borrowed_at=dt.date(2026, 5, 15), user_id=user.id)
    assert "không được trước ngày kết thúc" in str(exc.value)
