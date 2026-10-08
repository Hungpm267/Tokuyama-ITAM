"""Router xuất khẩu dữ liệu định dạng CSV (FR-18).

Bảo mật & Bất biến:
- Kiểm tra quyền truy cập qua dependency `require(module, PermissionAction.VIEW)`.
- TUYỆT ĐỐI KHÔNG xuất các trường trong REDACTED_FIELDS (pc_password_enc, email_password_enc,
  license_key_enc, password_hash) theo quy tắc bất biến GEMINI.md.
- Sử dụng mã hoá UTF-8 kèm BOM (\ufeff) để đảm bảo Excel hiển thị chính xác tiếng Việt và tiếng Nhật.
"""

from __future__ import annotations

import csv
import io
from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.permissions import require
from app.db import get_db
from app.enums import Module, PermissionAction
from app.models import (
    AccessCard,
    Asset,
    Assignment,
    CardLoan,
    Contract,
    License,
    Person,
    Phone,
)

router = APIRouter(prefix="/admin/export", tags=["Export"])


@router.get("/assets")
def export_assets_csv(
    db: Session = Depends(get_db),
    _actor=Depends(require(Module.ASSETS, PermissionAction.VIEW)),
) -> Response:
    """Xuất danh sách thiết bị tài sản IT sang file CSV (FR-18)."""
    output = io.StringIO()
    output.write("\ufeff")  # UTF-8 BOM
    writer = csv.writer(output)

    writer.writerow([
        "ID",
        "Mã tem GA",
        "Mã Vendor",
        "Loại thiết bị",
        "Model",
        "Form Factor",
        "Số Serial",
        "HWID",
        "MAC Ethernet",
        "MAC Wi-Fi",
        "Trạng thái",
        "Người đang sử dụng",
        "Ghi chú",
    ])

    assets = db.scalars(
        select(Asset)
        .options(
            selectinload(Asset.category),
            selectinload(Asset.assignments).selectinload(Assignment.person),
        )
        .where(Asset.is_deleted.is_(False))
        .order_by(Asset.id.asc())
    ).all()

    for a in assets:
        writer.writerow([
            a.id,
            a.asset_code or "",
            a.vendor_code or "",
            a.category.name_en if a.category else "",
            a.model or "",
            a.form_factor or "",
            a.serial or "",
            a.hwid or "",
            a.mac_ethernet or "",
            a.mac_wifi or "",
            a.status.value if hasattr(a.status, "value") else str(a.status),
            a.current_holder or "",
            a.note or "",
        ])

    return Response(
        content=output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=itam_assets.csv"},
    )


@router.get("/licenses")
def export_licenses_csv(
    db: Session = Depends(get_db),
    _actor=Depends(require(Module.LICENSES, PermissionAction.VIEW)),
) -> Response:
    """Xuất danh sách bản quyền phần mềm sang file CSV (FR-18).
    
    LƯU Ý: KHÔNG bao giờ xuất license_key_enc!
    """
    output = io.StringIO()
    output.write("\ufeff")
    writer = csv.writer(output)

    writer.writerow([
        "ID",
        "Sản phẩm phần mềm",
        "Nhà cung cấp",
        "Loại bản quyền",
        "Tổng số Seats",
        "Đã cấp phát",
        "Còn trống",
        "Ngày bắt đầu",
        "Ngày hết hạn",
        "Mã hợp đồng",
        "Ghi chú",
    ])

    licenses = db.scalars(
        select(License)
        .options(
            selectinload(License.product),
            selectinload(License.assignments),
        )
        .where(License.is_deleted.is_(False))
        .order_by(License.id.asc())
    ).all()

    for lic in licenses:
        assigned = sum(1 for asgn in lic.assignments if asgn.removed_at is None and not asgn.is_deleted)
        remaining = max(0, lic.seats - assigned)
        writer.writerow([
            lic.id,
            lic.product.name if lic.product else "",
            lic.product.vendor if lic.product and lic.product.vendor else "",
            lic.product.license_type.value if lic.product and lic.product.license_type else "",
            lic.seats,
            assigned,
            remaining,
            lic.start_date.isoformat() if lic.start_date else "",
            lic.expiry_date.isoformat() if lic.expiry_date else "Vĩnh viễn",
            lic.contract_id or "",
            lic.note or "",
        ])

    return Response(
        content=output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=itam_licenses.csv"},
    )


@router.get("/cards")
def export_cards_csv(
    db: Session = Depends(get_db),
    _actor=Depends(require(Module.CARDS, PermissionAction.VIEW)),
) -> Response:
    """Xuất danh sách thẻ ra vào sang file CSV (FR-18)."""
    output = io.StringIO()
    output.write("\ufeff")
    writer = csv.writer(output)

    writer.writerow([
        "ID",
        "Số thẻ",
        "Loại thẻ",
        "Trạng thái",
        "Người đang mượn",
        "Ghi chú",
    ])

    cards = db.scalars(
        select(AccessCard)
        .options(selectinload(AccessCard.loans).selectinload(CardLoan.person))
        .where(AccessCard.is_deleted.is_(False))
        .order_by(AccessCard.id.asc())
    ).all()

    for c in cards:
        writer.writerow([
            c.id,
            c.card_no,
            c.card_type.value if hasattr(c.card_type, "value") else str(c.card_type),
            c.status.value if hasattr(c.status, "value") else str(c.status),
            c.current_borrower or "",
            c.note or "",
        ])

    return Response(
        content=output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=itam_access_cards.csv"},
    )


@router.get("/persons")
def export_persons_csv(
    db: Session = Depends(get_db),
    _actor=Depends(require(Module.PERSONS, PermissionAction.VIEW)),
) -> Response:
    """Xuất danh sách nhân sự sang file CSV (FR-18).
    
    LƯU Ý: KHÔNG bao giờ xuất mật khẩu hay trường trong person_secrets!
    """
    output = io.StringIO()
    output.write("\ufeff")
    writer = csv.writer(output)

    writer.writerow([
        "ID",
        "Mã nhân viên",
        "User Login ID",
        "Họ và tên",
        "Phòng ban",
        "Email",
        "Trạng thái",
        "Ngày vào làm",
        "Ghi chú",
    ])

    persons = db.scalars(
        select(Person)
        .options(selectinload(Person.department))
        .where(Person.is_deleted.is_(False))
        .order_by(Person.id.asc())
    ).all()

    for p in persons:
        dept_name = p.department.name_en if p.department else ""
        writer.writerow([
            p.id,
            p.staff_code,
            p.user_login_id or "",
            p.full_name,
            dept_name,
            p.email or "",
            p.status.value if hasattr(p.status, "value") else str(p.status),
            p.start_working_date.isoformat() if p.start_working_date else "",
            p.note or "",
        ])

    return Response(
        content=output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=itam_employees.csv"},
    )


@router.get("/phones")
def export_phones_csv(
    db: Session = Depends(get_db),
    _actor=Depends(require(Module.PHONES, PermissionAction.VIEW)),
) -> Response:
    """Xuất danh bạ điện thoại máy nhánh sang file CSV (FR-18)."""
    output = io.StringIO()
    output.write("\ufeff")
    writer = csv.writer(output)

    writer.writerow([
        "ID",
        "Số máy nhánh (Extension)",
        "Tên máy điện thoại",
        "Loại thiết bị",
        "Vị trí đặt",
        "Trạng thái hoạt động",
        "Ghi chú",
    ])

    phones = db.scalars(
        select(Phone)
        .options(selectinload(Phone.location))
        .where(Phone.is_deleted.is_(False))
        .order_by(Phone.extension_number.asc().nulls_last(), Phone.device_name.asc())
    ).all()

    for ph in phones:
        loc_str = str(ph.location) if ph.location else ""
        writer.writerow([
            ph.id,
            ph.extension_number or "",
            ph.device_name,
            ph.device_type.value if hasattr(ph.device_type, "value") else str(ph.device_type),
            loc_str,
            "Hoạt động" if ph.is_active else "Ngừng hoạt động",
            ph.remarks or "",
        ])

    return Response(
        content=output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=itam_phone_directory.csv"},
    )


@router.get("/contracts")
def export_contracts_csv(
    db: Session = Depends(get_db),
    _actor=Depends(require(Module.CONTRACTS, PermissionAction.VIEW)),
) -> Response:
    """Xuất danh sách hợp đồng mua sắm sang file CSV (FR-18)."""
    output = io.StringIO()
    output.write("\ufeff")
    writer = csv.writer(output)

    writer.writerow([
        "ID",
        "Mã hợp đồng",
        "Nhà cung cấp",
        "Ngày ký",
        "Tình trạng giao nhận",
        "Ghi chú",
    ])

    contracts = db.scalars(
        select(Contract)
        .where(Contract.is_deleted.is_(False))
        .order_by(Contract.id.asc())
    ).all()

    for c in contracts:
        writer.writerow([
            c.id,
            c.code,
            c.vendor_name or "",
            c.signed_date.isoformat() if c.signed_date else "",
            c.delivery_status.value if hasattr(c.delivery_status, "value") else str(c.delivery_status),
            c.note or "",
        ])

    return Response(
        content=output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=itam_contracts.csv"},
    )

