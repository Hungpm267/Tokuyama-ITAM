"""Ngày "hôm nay" theo giờ làm việc của công ty.

Vì sao không dùng `dt.date.today()`: hàm đó lấy múi giờ của máy chủ. Container
trên cloud chạy UTC, nên từ 00:00 đến 06:59 giờ Việt Nam máy chủ vẫn ở ngày hôm
trước và mọi lượt bàn giao/thu hồi "hôm nay" bị từ chối là ngày tương lai.

Dùng offset cố định thay cho `zoneinfo` vì Việt Nam không có giờ mùa hè và
Windows không kèm sẵn dữ liệu tz (sẽ phải thêm thư viện `tzdata`).
"""

from __future__ import annotations

import datetime as dt

BUSINESS_TZ = dt.timezone(dt.timedelta(hours=7), name="Asia/Ho_Chi_Minh")


def _now_utc() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def today_local(now: dt.datetime | None = None) -> dt.date:
    """Ngày hiện tại theo giờ Việt Nam (UTC+7)."""
    moment = now if now is not None else _now_utc()
    return moment.astimezone(BUSINESS_TZ).date()
