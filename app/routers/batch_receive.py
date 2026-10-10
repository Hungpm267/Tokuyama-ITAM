"""Router cho tính năng Nhập kho thiết bị theo lô từ Hạng mục Hợp đồng."""

from __future__ import annotations

import re
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.admin import get_admin, invalidate_model_count_cache
from app.core.audit import record_audit
from app.core.i18n import get_current_lang
from app.core.inputs import optional_text, read_json_object, require_positive_int
from app.core.permissions import has_permission
from app.core.security import verify_session_token
from app.db import get_db
from app.enums import AssetStatus, AuditAction, ContractItemKind, Module, PermissionAction
from app.models import Asset, AssetCategory, Contract, ContractLine, User
from app.services.contract_service import sync_contract_delivery_status

router = APIRouter(prefix="/admin/contract-line", tags=["Batch Receive"])


def get_current_actor(request: Request, db: Session) -> User:
    """Xác thực người dùng từ session hoặc cookie itam_session."""
    user_id = request.session.get("user_id") if hasattr(request, "session") else None

    if not user_id:
        token = request.cookies.get("itam_session")
        if token:
            payload = verify_session_token(token)
            if payload and "user_id" in payload:
                user_id = payload["user_id"]

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Yêu cầu đăng nhập để thực hiện thao tác.",
        )

    user = db.scalar(
        select(User).where(
            User.id == int(user_id),
            User.is_active.is_(True),
            User.is_deleted.is_(False),
        )
    )
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Tài khoản không tồn tại hoặc đã bị khóa.",
        )
    return user


def check_batch_receive_permission(db: Session, user: User) -> None:
    """Kiểm tra quyền nhập thiết bị vào kho."""
    # Yêu cầu quyền ADD trên module ASSETS
    if not has_permission(db, user, Module.ASSETS, PermissionAction.ADD):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bạn không có quyền thực hiện thao tác này.",
        )


@router.get("/{line_id}/receive", response_class=HTMLResponse)
async def batch_receive_page(
    line_id: int,
    request: Request,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Hiển thị trang giao diện Nhập kho theo lô cho một Hạng mục Hợp đồng."""
    user = get_current_actor(request, db)

    # Hạng mục phần mềm không có serial để nhập: chuyển sang màn hình nhận phần mềm TRƯỚC
    # khi kiểm quyền nhập thiết bị - màn hình đó tự kiểm quyền của nó (licenses, add).
    kind = db.scalar(
        select(ContractLine.item_kind).where(ContractLine.id == line_id, ContractLine.is_deleted.is_(False))
    )
    if kind == ContractItemKind.SOFTWARE:
        return RedirectResponse(f"/admin/contract-line/{line_id}/receive-software", status_code=303)

    check_batch_receive_permission(db, user)

    line = db.scalar(
        select(ContractLine)
        .options(
            selectinload(ContractLine.contract).selectinload(Contract.lines),
            selectinload(ContractLine.assets),
        )
        .where(ContractLine.id == line_id, ContractLine.is_deleted.is_(False))
    )
    if not line:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Hạng mục hợp đồng không tồn tại hoặc đã bị xóa.",
        )

    # Danh mục loại tài sản
    categories = db.scalars(
        select(AssetCategory)
        .where(AssetCategory.is_deleted.is_(False))
        .order_by(AssetCategory.id)
    ).all()

    # Đoán Category ID phù hợp dựa trên item_type
    suggested_category_id: int | None = None
    item_type_lower = (line.item_type or "").lower()
    for cat in categories:
        cat_en = (cat.name_en or "").lower()
        cat_ja = (cat.name_ja or "").lower()
        if (cat_en and cat_en in item_type_lower) or (cat_ja and cat_ja in item_type_lower):
            suggested_category_id = cat.id
            break

    # Phỏng đoán các từ khóa thông dụng nếu chưa khớp
    if not suggested_category_id:
        if "laptop" in item_type_lower or "xách tay" in item_type_lower:
            for cat in categories:
                if "laptop" in (cat.name_en or "").lower():
                    suggested_category_id = cat.id
                    break
        elif "pc" in item_type_lower or "desktop" in item_type_lower or "máy bàn" in item_type_lower:
            for cat in categories:
                if "desktop" in (cat.name_en or "").lower() or "pc" in (cat.name_en or "").lower():
                    suggested_category_id = cat.id
                    break

    if not suggested_category_id and categories:
        suggested_category_id = categories[0].id

    # Đoán Form Factor
    suggested_form_factor = "Laptop" if "laptop" in item_type_lower else (
        "Desktop" if ("pc" in item_type_lower or "desktop" in item_type_lower) else "Standard"
    )

    # Đoán Model từ spec hoặc item_type
    suggested_model = line.item_type
    if line.spec:
        first_line = line.spec.strip().split("\n")[0].strip()
        if len(first_line) < 60:
            suggested_model = first_line

    # Gợi ý mã GA tiếp theo
    existing_codes = db.scalars(
        select(Asset.asset_code)
        .where(Asset.is_deleted.is_(False), Asset.asset_code.is_not(None))
        .order_by(Asset.id.desc())
        .limit(100)
    ).all()

    next_prefix = "TVC-EM"
    next_num = 1
    max_num = 0
    pattern = re.compile(r"^(TVC-[A-Za-z]+)(\d+)$")
    for code in existing_codes:
        if not code:
            continue
        m = pattern.match(code.strip())
        if m:
            prefix, num_str = m.groups()
            num = int(num_str)
            if num > max_num:
                max_num = num
                next_prefix = prefix
    if max_num > 0:
        next_num = max_num + 1

    admin = get_admin()
    if not admin:
        raise HTTPException(status_code=500, detail="Giao diện quản trị chưa sẵn sàng.")

    current_lang = get_current_lang(request)
    context = {
        "request": request,
        "admin": admin,
        "contract_line": line,
        "contract": line.contract,
        "categories": categories,
        "suggested_category_id": suggested_category_id,
        "suggested_model": suggested_model,
        "suggested_form_factor": suggested_form_factor,
        "next_asset_code_prefix": next_prefix,
        "next_asset_code_num": next_num,
        "qty_remaining": line.qty_remaining,
        "current_lang": current_lang,
    }
    return await admin.templates.TemplateResponse(request, "sqladmin/batch_receive.html", context)


@router.post("/{line_id}/receive")
async def process_batch_receive(
    line_id: int,
    request: Request,
    db: Session = Depends(get_db),
) -> JSONResponse:
    """Xử lý tiếp nhận và tạo đồng loạt danh sách thiết bị cho Hạng mục Hợp đồng."""
    user = get_current_actor(request, db)
    check_batch_receive_permission(db, user)

    line = db.scalar(
        select(ContractLine)
        .options(
            selectinload(ContractLine.contract).selectinload(Contract.lines),
            selectinload(ContractLine.assets),
        )
        .where(ContractLine.id == line_id, ContractLine.is_deleted.is_(False))
    )
    if not line:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Hạng mục hợp đồng không tồn tại hoặc đã bị xóa.",
        )
    if not line.contract or line.contract.is_deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Hợp đồng của hạng mục này không tồn tại hoặc đã bị xóa.",
        )
    if line.item_kind == ContractItemKind.SOFTWARE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Hạng mục này là phần mềm, không thể nhập kho bằng thiết bị.",
        )

    body = await read_json_object(request)

    if not body.get("category_id"):
        raise HTTPException(status_code=400, detail="Vui lòng chọn Loại tài sản (Category).")
    category_pk = require_positive_int(body.get("category_id"), "Loại tài sản không hợp lệ hoặc đã bị xóa.")

    cat = db.scalar(
        select(AssetCategory).where(
            AssetCategory.id == category_pk,
            AssetCategory.is_deleted.is_(False),
        )
    )
    if not cat:
        raise HTTPException(status_code=400, detail="Loại tài sản không hợp lệ hoặc đã bị xóa.")

    # Độ dài theo đúng cột trong bảng assets: quá dài thì báo 400 thay vì để DB ném lỗi 500.
    model = optional_text(body.get("model"), 150, "Model thiết bị") or ""
    form_factor = optional_text(body.get("form_factor"), 30, "Kiểu dáng") or ""
    batch_note = optional_text(body.get("note"), 2000, "Ghi chú") or ""
    items_raw = body.get("items", [])

    if not items_raw or not isinstance(items_raw, list):
        raise HTTPException(
            status_code=400,
            detail="Danh sách thiết bị trống. Vui lòng nhập ít nhất 1 thiết bị để tiếp nhận.",
        )

    cleaned_items: list[dict[str, str | None]] = []
    seen_serials: set[str] = set()
    seen_asset_codes: set[str] = set()
    seen_vendor_codes: set[str] = set()

    for idx, item in enumerate(items_raw, 1):
        if not isinstance(item, dict):
            continue
        serial = optional_text(item.get("serial"), 100, f"Dòng {idx}: Số Serial")
        asset_code = optional_text(item.get("asset_code"), 50, f"Dòng {idx}: Mã GA")
        vendor_code = optional_text(item.get("vendor_code"), 50, f"Dòng {idx}: Mã Vendor")
        mac_eth = optional_text(item.get("mac_ethernet"), 20, f"Dòng {idx}: MAC Ethernet")
        mac_wifi = optional_text(item.get("mac_wifi"), 20, f"Dòng {idx}: MAC Wi-Fi")
        note = optional_text(item.get("note"), 2000, f"Dòng {idx}: Ghi chú")

        # Check constraint DB: asset_code IS NOT NULL OR vendor_code IS NOT NULL OR serial IS NOT NULL
        if not serial and not asset_code and not vendor_code:
            raise HTTPException(
                status_code=400,
                detail=f"Dòng {idx}: Phải có ít nhất một trong các thông tin: Số Serial, Mã tem GA hoặc Mã Vendor.",
            )

        # Kiểm tra trùng lặp trong nội bộ danh sách gửi lên
        if serial:
            s_lower = serial.lower()
            if s_lower in seen_serials:
                raise HTTPException(
                    status_code=400,
                    detail=f"Dòng {idx}: Số Serial '{serial}' bị lặp lại trong danh sách đang nhập.",
                )
            seen_serials.add(s_lower)

        if asset_code:
            a_lower = asset_code.lower()
            if a_lower in seen_asset_codes:
                raise HTTPException(
                    status_code=400,
                    detail=f"Dòng {idx}: Mã GA '{asset_code}' bị lặp lại trong danh sách đang nhập.",
                )
            seen_asset_codes.add(a_lower)

        if vendor_code:
            v_lower = vendor_code.lower()
            if v_lower in seen_vendor_codes:
                raise HTTPException(
                    status_code=400,
                    detail=f"Dòng {idx}: Mã Vendor '{vendor_code}' bị lặp lại trong danh sách đang nhập.",
                )
            seen_vendor_codes.add(v_lower)

        cleaned_items.append({
            "serial": serial,
            "asset_code": asset_code,
            "vendor_code": vendor_code,
            "mac_ethernet": mac_eth,
            "mac_wifi": mac_wifi,
            "note": note,
        })

    if not cleaned_items:
        raise HTTPException(status_code=400, detail="Không có dòng thiết bị hợp lệ để nhập kho.")

    # Kiểm tra số lượng nhập không vượt quá số lượng còn lại của hạng mục hợp đồng
    if len(cleaned_items) > line.qty_remaining:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Số lượng nhập ({len(cleaned_items)} thiết bị) vượt quá số lượng còn lại "
                f"của hạng mục hợp đồng ({line.qty_remaining} thiết bị còn lại)."
            ),
        )

    # Kiểm tra trùng lặp với CSDL hiện có (lọc is_deleted = False theo GEMINI.md)
    all_serials = [it["serial"] for it in cleaned_items if it["serial"]]
    if all_serials:
        existing_serials = db.execute(
            select(Asset.serial, Asset.asset_code)
            .where(Asset.is_deleted.is_(False), func.lower(Asset.serial).in_([v.lower() for v in all_serials]))
        ).all()
        if existing_serials:
            dup_serial, dup_asset = existing_serials[0]
            ref_info = f" (đã gán cho thiết bị {dup_asset})" if dup_asset else ""
            raise HTTPException(
                status_code=400,
                detail=f"Số Serial '{dup_serial}' đã tồn tại trong hệ thống{ref_info}! Vui lòng kiểm tra lại.",
            )

    all_asset_codes = [it["asset_code"] for it in cleaned_items if it["asset_code"]]
    if all_asset_codes:
        existing_assets = db.execute(
            select(Asset.asset_code)
            .where(Asset.is_deleted.is_(False), func.lower(Asset.asset_code).in_([v.lower() for v in all_asset_codes]))
        ).all()
        if existing_assets:
            dup_code = existing_assets[0][0]
            raise HTTPException(
                status_code=400,
                detail=f"Mã GA '{dup_code}' đã tồn tại trong hệ thống! Vui lòng chọn mã khác.",
            )

    all_vendor_codes = [it["vendor_code"] for it in cleaned_items if it["vendor_code"]]
    if all_vendor_codes:
        existing_vendors = db.execute(
            select(Asset.vendor_code)
            .where(Asset.is_deleted.is_(False), func.lower(Asset.vendor_code).in_([v.lower() for v in all_vendor_codes]))
        ).all()
        if existing_vendors:
            dup_vcode = existing_vendors[0][0]
            raise HTTPException(
                status_code=400,
                detail=f"Mã Vendor '{dup_vcode}' đã tồn tại trong hệ thống! Vui lòng chọn mã khác.",
            )

    # Transaction: Tạo Asset hàng loạt
    client_ip = request.client.host if request.client else None
    created_assets: list[Asset] = []

    for item in cleaned_items:
        combined_note = item["note"] or batch_note or None
        if item["note"] and batch_note:
            combined_note = f"{batch_note}; {item['note']}"

        asset = Asset(
            category_id=category_pk,
            contract_line_id=line.id,
            contract_line=line,
            model=model or None,
            form_factor=form_factor or None,
            serial=item["serial"],
            asset_code=item["asset_code"],
            vendor_code=item["vendor_code"],
            mac_ethernet=item["mac_ethernet"],
            mac_wifi=item["mac_wifi"],
            status=AssetStatus.IN_STOCK,
            note=combined_note,
            created_by=user.id,
        )
        db.add(asset)
        created_assets.append(asset)

    db.flush()

    # Ghi audit log cho từng thiết bị được tạo
    for asset in created_assets:
        record_audit(
            db=db,
            action=AuditAction.CREATE,
            table_name="assets",
            record_id=asset.id,
            user_id=user.id,
            after={
                "id": asset.id,
                "contract_line_id": line.id,
                "category_id": asset.category_id,
                "model": asset.model,
                "form_factor": asset.form_factor,
                "serial": asset.serial,
                "asset_code": asset.asset_code,
                "vendor_code": asset.vendor_code,
                "mac_ethernet": asset.mac_ethernet,
                "mac_wifi": asset.mac_wifi,
                "status": asset.status.value,
            },
            ip_address=client_ip,
        )

    # Cập nhật tiến độ hợp đồng bằng cùng một phép tính với mọi nơi khác
    # (hợp đồng có thể gồm cả hạng mục phần mềm, đếm theo seat chứ không theo thiết bị).
    db.flush()
    sync_contract_delivery_status(db, line.contract.id)

    db.commit()
    invalidate_model_count_cache(Asset)

    return JSONResponse(
        content={
            "success": True,
            "count": len(created_assets),
            "message": f"Đã nhập kho thành công {len(created_assets)} thiết bị cho hạng mục '{line.item_type}'.",
            "redirect_url": f"/admin/contract-line/details/{line.id}",
        }
    )
