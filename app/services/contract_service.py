"""Dịch vụ nghiệp vụ Quản lý Hợp đồng và Đối soát giao nhận thiết bị (Phase 4 - FR-14)."""

from __future__ import annotations

from typing import Any
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Asset, Contract, ContractLine


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
        delivered = (
            db.scalar(
                select(func.count(Asset.id)).where(
                    Asset.contract_line_id == line.id,
                    Asset.is_deleted.is_(False),
                )
            )
            or 0
        )
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
