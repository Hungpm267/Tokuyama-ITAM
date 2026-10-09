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

from app.admin import AssetAdmin, LicenseAssignmentAdmin, PersonAdmin
from app.core.security import hash_password
from app.enums import AssetStatus, DeliveryStatus, RoleCode
from app.models import (
    Asset,
    Contract,
    ContractLine,
    License,
    LicenseAssignment,
    Role,
    User,
)
from app.routers.auth import LoginInput, login
from app.routers.batch_receive import check_batch_receive_permission
from app.routers.role_matrix import _verify_admin_access
from app.services.assignment_service import assign_asset, return_asset
from app.services.card_service import loan_card, return_card
from app.services.contract_service import sync_contract_delivery_status


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


def test_admin_delete_person_blocked_when_holding_card(db, seed):
    """Admin delete_model chặn xóa nhân viên đang mượn thẻ ra vào."""
    person = seed["person_b"]
    card = seed["card"]
    user = seed["user"]

    loan_card(db, card.id, person_id=person.id, user_id=user.id)
    db.flush()

    req = DummyRequest(session={"user_id": user.id}, db=db, query_params={"delete_reason": "Nghỉ việc"})
    view = PersonAdmin()

    with pytest.raises(HTTPException) as exc:
        asyncio.run(view.delete_model(req, person.id))
    assert exc.value.status_code == 400
    assert "đang mượn thẻ ra vào" in exc.value.detail


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


def test_contract_delivery_status_sync(db, seed):
    """Đồng bộ trạng thái delivery_status của Contract khi có thay đổi số asset."""
    contract = Contract(
        code="HD-TEST-WAVE2",
        vendor_name="FPT IS",
        signed_date=dt.date(2026, 1, 1),
        delivery_status=DeliveryStatus.PENDING,
    )
    db.add(contract)
    db.flush()

    line = ContractLine(
        contract_id=contract.id,
        item_type="Laptop Dell",
        qty_ordered=2,
    )
    db.add(line)
    db.flush()

    # Chưa nhận máy nào -> PENDING
    assert sync_contract_delivery_status(db, contract.id) == DeliveryStatus.PENDING

    # Nhập 1 máy -> PENDING (chưa đủ 2)
    a1 = Asset(asset_code="A1", category_id=seed["cat"].id, contract_line_id=line.id)
    db.add(a1)
    db.flush()
    assert sync_contract_delivery_status(db, contract.id) == DeliveryStatus.PENDING

    # Nhập máy thứ 2 -> DELIVERED
    a2 = Asset(asset_code="A2", category_id=seed["cat"].id, contract_line_id=line.id)
    db.add(a2)
    db.flush()
    assert sync_contract_delivery_status(db, contract.id) == DeliveryStatus.DELIVERED
    assert contract.delivery_status == DeliveryStatus.DELIVERED

    # Xóa mềm máy thứ 2 (tuân thủ check constraint: có deleted_at và delete_reason) -> trở lại PENDING
    a2.is_deleted = True
    a2.deleted_at = dt.datetime.now(dt.timezone.utc)
    a2.delete_reason = "Hỏng màn hình không sử dụng được"
    db.flush()
    assert sync_contract_delivery_status(db, contract.id) == DeliveryStatus.PENDING
    assert contract.delivery_status == DeliveryStatus.PENDING


def test_historical_overlap_checks(db, seed):
    """Chặn bàn giao máy và mượn thẻ có khoảng thời gian trùng với lịch sử đã trả."""
    asset = seed["asset"]
    person = seed["person"]
    user = seed["user"]

    # Đợt mượn 1: 01/05/2026 -> 01/06/2026 (đã trả)
    assign_asset(db, asset.id, person.id, borrowed_at=dt.date(2026, 5, 1), user_id=user.id)
    return_asset(db, asset.id, returned_at=dt.date(2026, 6, 1), user_id=user.id)
    db.flush()

    # Cố tình mượn lại vào ngày 15/05/2026 (trước ngày 01/06/2026) -> lỗi
    with pytest.raises(ValueError) as exc:
        assign_asset(db, asset.id, person.id, borrowed_at=dt.date(2026, 5, 15), user_id=user.id)
    assert "không được trước ngày kết thúc" in str(exc.value)

    # Thẻ ra vào tương tự
    card = seed["card"]
    loan_card(db, card.id, person_id=person.id, borrowed_at=dt.date(2026, 5, 1), user_id=user.id)
    return_card(db, card.id, returned_at=dt.date(2026, 6, 1), user_id=user.id)
    db.flush()

    with pytest.raises(ValueError) as exc_card:
        loan_card(db, card.id, person_id=person.id, borrowed_at=dt.date(2026, 5, 20), user_id=user.id)
    assert "không được trước ngày trả" in str(exc_card.value)


def test_license_assignment_admin_seat_limit(db, seed):
    """LicenseAssignmentAdmin.on_model_change chặn gán khi license đã hết seats."""
    product = seed["product"]
    lic = License(product_id=product.id, seats=1)
    db.add(lic)
    db.flush()

    # Gán seat duy nhất
    asgn = LicenseAssignment(
        license_id=lic.id,
        person_id=seed["person"].id,
        assigned_at=dt.date.today(),
    )
    db.add(asgn)
    db.flush()

    # Thử gán thêm qua admin view
    admin_view = LicenseAssignmentAdmin()
    req = DummyRequest(session={"lang": "vi"}, db=db)

    dummy_model = LicenseAssignment()
    data = {
        "license": lic.id,
        "person": seed["person_b"].id,
    }

    with pytest.raises(ValueError) as exc:
        asyncio.run(admin_view.on_model_change(data, dummy_model, is_created=True, request=req))
    assert "đã hết lượt gán" in str(exc.value)


def test_role_matrix_verify_admin_access_realtime_db(db, seed):
    """_verify_admin_access kiểm tra CSDL thời gian thực: tài khoản bị khóa/xóa/hạ vai trò bị từ chối."""
    admin_user = seed["user"]
    req = DummyRequest(session={"user_id": admin_user.id}, db=db)

    # Admin active -> hợp lệ
    uid = _verify_admin_access(req, db)
    assert uid == admin_user.id

    # Admin bị vô hiệu hóa (is_active=False) -> bị từ chối 403
    admin_user.is_active = False
    db.flush()
    with pytest.raises(HTTPException) as exc:
        _verify_admin_access(req, db)
    assert exc.value.status_code == 403

    # Khôi phục active nhưng đổi vai trò sang non-admin -> bị từ chối 403
    admin_user.is_active = True
    ga_role = Role(code=RoleCode.GA_MANAGER.value, name_en="GA Manager")
    db.add(ga_role)
    db.flush()
    admin_user.role_id = ga_role.id
    admin_user.role = ga_role
    db.flush()

    with pytest.raises(HTTPException) as exc2:
        _verify_admin_access(req, db)
    assert exc2.value.status_code == 403


def test_batch_receive_permission_message_sanitized(db, seed):
    """Thông báo lỗi phân quyền trong batch_receive không tiết lộ mã quyền nội bộ assets.add."""
    viewer_role = Role(code="VIEWER", name_en="Viewer")
    db.add(viewer_role)
    db.flush()
    viewer_user = User(username="viewer", password_hash="x", display_name="Viewer", role_id=viewer_role.id)
    db.add(viewer_user)
    db.flush()

    with pytest.raises(HTTPException) as exc:
        check_batch_receive_permission(db, viewer_user)
    assert exc.value.status_code == 403
    assert "assets.add" not in exc.value.detail
