"""Cổng xem mật khẩu nhân viên (FR-06).

Luồng theo BRD mục "Lưu và xem mật khẩu nhân viên":
  1. Người dùng phải có quyền (secrets, view) - chỉ Admin.
  2. Màn hình luôn hiện ••••••.
  3. Bấm "Xem" -> nhập lại mật khẩu ĐĂNG NHẬP của chính mình.
  4. Đúng -> cấp reveal token sống 2 phút cho phiên hiện tại.
  5. Giá trị thật tự ẩn sau 60 giây ở phía trình duyệt.
  6. Mỗi lần giải mã thành công ghi một dòng audit REVEAL.
  7. Sai 5 lần trong 15 phút -> khoá chức năng 15 phút.
  8. CHỈ endpoint POST /persons/{id}/secrets/reveal trả giá trị thật.

Module này là logic thuần, không phụ thuộc FastAPI, để test được. Lớp route chỉ
gọi vào đây.

LƯU Ý VỀ TRẠNG THÁI: bộ đếm sai và token lưu trong bộ nhớ tiến trình. Đúng với
đợt 1 (một tiến trình uvicorn, 5 người dùng). Khi chạy nhiều worker, chuyển sang
Redis hoặc một bảng DB - đừng tăng số worker mà quên việc này, vì bộ đếm khoá sẽ
bị chia nhỏ theo worker và kẻ tấn công được thử nhiều hơn 5 lần.
"""

from __future__ import annotations

import datetime as dt
import secrets
from dataclasses import dataclass, field

TOKEN_TTL = dt.timedelta(minutes=2)
LOCKOUT_WINDOW = dt.timedelta(minutes=15)
LOCKOUT_DURATION = dt.timedelta(minutes=15)
MAX_FAILURES = 5
AUTO_HIDE_SECONDS = 60  # phía trình duyệt


class RevealDenied(Exception):
    """Từ chối cấp quyền xem. `reason` dùng cho audit, KHÔNG trả nguyên văn ra UI."""

    def __init__(self, reason: str, retry_after: dt.timedelta | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.retry_after = retry_after


@dataclass
class _UserState:
    failures: list[dt.datetime] = field(default_factory=list)
    locked_until: dt.datetime | None = None
    token: str | None = None
    token_expires_at: dt.datetime | None = None


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class RevealGate:
    """Quản lý việc xác minh lại và vòng đời reveal token."""

    def __init__(self, now=_now) -> None:
        self._state: dict[int, _UserState] = {}
        self._now = now

    def _st(self, user_id: int) -> _UserState:
        return self._state.setdefault(user_id, _UserState())

    # -- bước 3 + 4: xác minh lại và cấp token ---------------------------

    def authorize(
        self, user_id: int, password: str, password_hash: str, verifier
    ) -> str:
        """Xác minh mật khẩu đăng nhập, trả về reveal token.

        `verifier(password, password_hash) -> bool` là hàm kiểm tra Argon2id,
        truyền từ ngoài vào để module này test được mà không cần băm thật.
        Ném RevealDenied nếu đang bị khoá hoặc mật khẩu sai.
        """
        now = self._now()
        st = self._st(user_id)

        if st.locked_until and now < st.locked_until:
            raise RevealDenied("locked", retry_after=st.locked_until - now)

        if not verifier(password, password_hash):
            st.failures = [t for t in st.failures if now - t < LOCKOUT_WINDOW]
            st.failures.append(now)
            if len(st.failures) >= MAX_FAILURES:
                st.locked_until = now + LOCKOUT_DURATION
                st.failures.clear()
                raise RevealDenied("locked", retry_after=LOCKOUT_DURATION)
            raise RevealDenied("bad_password")

        st.failures.clear()
        st.locked_until = None
        st.token = secrets.token_urlsafe(32)
        st.token_expires_at = now + TOKEN_TTL
        return st.token

    # -- bước 5: dùng token để xem thêm bản ghi khác ---------------------

    def check_token(self, user_id: int, token: str | None) -> None:
        """Ném RevealDenied nếu token thiếu, sai hoặc hết hạn."""
        st = self._st(user_id)
        now = self._now()
        if st.locked_until and now < st.locked_until:
            raise RevealDenied("locked", retry_after=st.locked_until - now)
        if not st.token or not token:
            raise RevealDenied("no_token")
        if st.token_expires_at is None or now >= st.token_expires_at:
            self.revoke(user_id)
            raise RevealDenied("token_expired")
        # So sánh thời gian hằng định, tránh rò rỉ qua thời gian phản hồi.
        if not secrets.compare_digest(st.token, token):
            raise RevealDenied("bad_token")

    def revoke(self, user_id: int) -> None:
        """Gọi khi đăng xuất hoặc khi người dùng bấm 'Ẩn'."""
        st = self._st(user_id)
        st.token = None
        st.token_expires_at = None

    def is_locked(self, user_id: int) -> bool:
        st = self._st(user_id)
        return bool(st.locked_until and self._now() < st.locked_until)


def mask(value: str | None) -> str:
    """Giá trị hiển thị mặc định ở MỌI màn hình và MỌI response danh sách."""
    return "••••••" if value else ""
