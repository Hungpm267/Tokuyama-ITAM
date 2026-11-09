"""Mã nhân sự theo loại.

Nhân viên chính thức nhập mã TVC tay. Vendor và người Nhật công tác được app cấp mã
VND-NNN / JP-NNN, hoặc tự nhập đúng tiền tố. Mã đã dùng (kể cả bản ghi đã xóa mềm) không
cấp lại.
"""

from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.enums import PersonType
from app.models import Person

PREFIX = {PersonType.VENDOR: "VND-", PersonType.BUSINESS_TRIP: "JP-"}
_LABEL = {
    PersonType.EMPLOYEE: "Nhân viên chính thức",
    PersonType.VENDOR: "Vendor",
    PersonType.BUSINESS_TRIP: "Công tác Nhật",
}


def next_code(db: Session, person_type: PersonType) -> str:
    prefix = PREFIX[person_type]
    pattern = re.compile(re.escape(prefix) + r"(\d+)")
    codes = db.scalars(select(Person.staff_code).where(Person.staff_code.ilike(prefix + "%"))).all()
    numbers = [int(m.group(1)) for code in codes if (m := pattern.fullmatch(code.upper()))]
    return f"{prefix}{max(numbers, default=0) + 1:03d}"


def resolve_code(db: Session, person_type: PersonType, code: str | None) -> str:
    """Mã cuối cùng cho một nhân sự, hoặc ValueError nếu mã không khớp loại."""
    clean = (code or "").strip()
    upper = clean.upper()
    if person_type == PersonType.EMPLOYEE:
        if not clean:
            raise ValueError("Nhân viên chính thức phải có mã nhân viên.")
        if any(upper.startswith(p) for p in PREFIX.values()):
            raise ValueError("Mã VND- / JP- chỉ dành cho Vendor và người công tác Nhật. Hãy nhập mã nhân viên chính thức.")
        return clean
    if not clean:
        return next_code(db, person_type)
    prefix = PREFIX[person_type]
    if not upper.startswith(prefix):
        raise ValueError(f"Mã của {_LABEL[person_type]} phải bắt đầu bằng {prefix} (hoặc để trống để app tự cấp).")
    return upper
