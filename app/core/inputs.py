"""Kiểm tra kiểu dữ liệu đầu vào dùng chung cho các endpoint nhận JSON.

Các endpoint đọc `await request.json()` nhận được bất cứ thứ gì client gửi: một
mảng thay cho object, `true` thay cho mã số... Không kiểm tra thì hoặc lỗi 500,
hoặc tệ hơn là bị ép kiểu âm thầm (`int(True) == 1` -> thao tác lên bản ghi #1).
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request

#: Giới hạn trên của kiểu INTEGER trong PostgreSQL.
MAX_DB_INT = 2_147_483_647


async def read_json_object(request: Request) -> dict[str, Any]:
    """Đọc body JSON và bảo đảm nó là một object."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Dữ liệu JSON không hợp lệ.")
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Dữ liệu JSON không hợp lệ.")
    return body


def require_positive_int(raw: Any, message: str) -> int:
    """Số nguyên dương hợp lệ cho một cột INTEGER; sai thì trả 400 với `message`."""
    # bool là lớp con của int trong Python; `true` từ JSON không phải là một mã số.
    if isinstance(raw, bool) or not isinstance(raw, (int, str)):
        raise HTTPException(status_code=400, detail=message)
    try:
        value = int(str(raw).strip())
    except ValueError:
        raise HTTPException(status_code=400, detail=message)
    if value <= 0 or value > MAX_DB_INT:
        raise HTTPException(status_code=400, detail=message)
    return value


def optional_text(raw: Any, max_length: int, label: str) -> str | None:
    """Chuỗi tuỳ chọn đã cắt khoảng trắng; quá dài hoặc sai kiểu thì trả 400."""
    if raw is None:
        return None
    if not isinstance(raw, (str, int, float)) or isinstance(raw, bool):
        raise HTTPException(status_code=400, detail=f"{label} không hợp lệ.")
    text = str(raw).strip()
    if len(text) > max_length:
        raise HTTPException(status_code=400, detail=f"{label} quá dài (tối đa {max_length} ký tự).")
    return text or None
