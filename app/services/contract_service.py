"""Dịch vụ nghiệp vụ Quản lý Hợp đồng và Đối soát giao nhận thiết bị (Phase 4 - FR-14)."""

from __future__ import annotations

from typing import Any
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.enums import ContractItemKind, DeliveryStatus
from app.models import Asset, Contract, ContractLine, License


def line_received_qty(
    db: Session,
    line: ContractLine,
    exclude_asset_id: int | None = None,
    exclude_license_id: int | None = None,
) -> int:
    """Số đã nhận của một hạng mục - luôn TÍNH từ dữ liệu, không có cột gõ tay (Rule 8).

    Phần cứng: đếm thiết bị còn sống gắn vào hạng mục.
    Phần mềm: tổng seat của các gói license còn sống gắn vào hạng mục.
    Tham số exclude_* dùng khi kiểm tra sức chứa cho chính bản ghi đang được sửa.
    """
    if line.item_kind == ContractItemKind.SOFTWARE:
        stmt = select(func.coalesce(func.sum(License.seats), 0)).where(
            License.contract_line_id == line.id,
            License.is_deleted.is_(False),
        )
        if exclude_license_id:
            stmt = stmt.where(License.id != exclude_license_id)
        return int(db.scalar(stmt) or 0)

    stmt = select(func.count(Asset.id)).where(
        Asset.contract_line_id == line.id,
        Asset.is_deleted.is_(False),
    )
    if exclude_asset_id:
        stmt = stmt.where(Asset.id != exclude_asset_id)
    return int(db.scalar(stmt) or 0)


def get_contract_summary(db: Session, contract_id: int) -> dict[str, Any]:
    """Đối soát tiến độ giao nhận thiết bị của một Hợp đồng (Rule 8: đếm động từ Asset)."""
    contract = db.get(Contract, contract_id)
    if not contract or contract.is_deleted:
        raise ValueError(f"Hợp đồng ID {contract_id} không tồn tại hoặc đã bị xoá")

    lines = db.scalars(
        select(ContractLine)
        .where(
            ContractLine.contract_id == contract_id,
            ContractLine.is_deleted.is_(False),
        )
        .order_by(ContractLine.id)
    ).all()

    lines_summary: list[dict[str, Any]] = []
    total_ordered = 0
    total_delivered = 0

    for line in lines:
        ordered = line.qty_ordered
        delivered = line_received_qty(db, line)
        remaining = max(0, ordered - delivered)

        if delivered >= ordered:
            line_status = "FULL"
        elif delivered > 0:
            line_status = "PARTIAL"
        else:
            line_status = "PENDING"

        total_ordered += ordered
        total_delivered += delivered

        lines_summary.append(
            {
                "line": line,
                "line_id": line.id,
                "item_type": line.item_type,
                "qty_ordered": ordered,
                "qty_delivered": delivered,
                "qty_remaining": remaining,
                "status": line_status,
            }
        )

    total_remaining = max(0, total_ordered - total_delivered)
    if total_ordered > 0 and total_delivered >= total_ordered:
        contract_status = "FULL"
    elif total_delivered > 0:
        contract_status = "PARTIAL"
    else:
        contract_status = "PENDING"

    return {
        "contract": contract,
        "lines": lines_summary,
        "total_ordered": total_ordered,
        "total_delivered": total_delivered,
        "total_remaining": total_remaining,
        "status": contract_status,
    }


def sync_contract_delivery_status(db: Session, contract_id: int) -> DeliveryStatus | None:
    """Đồng bộ delivery_status của Contract dựa trên các lines và asset sống (Rule 8)."""
    contract = db.get(Contract, contract_id)
    if not contract or contract.is_deleted:
        return None

    lines = db.scalars(
        select(ContractLine).where(
            ContractLine.contract_id == contract_id,
            ContractLine.is_deleted.is_(False),
        )
    ).all()

    if not lines:
        contract.delivery_status = DeliveryStatus.PENDING
        return DeliveryStatus.PENDING

    all_delivered = True
    for line in lines:
        delivered = line_received_qty(db, line)
        if delivered < line.qty_ordered:
            all_delivered = False
            break

    new_status = DeliveryStatus.DELIVERED if all_delivered else DeliveryStatus.PENDING
    contract.delivery_status = new_status
    return new_status

