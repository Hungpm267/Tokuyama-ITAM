"""Bảo mật mật khẩu đăng nhập bằng thuật toán Argon2id và xác thực phiên.

Quy ước từ GEMINI.md:
- Băm bằng Argon2id (thư viện argon2-cffi).
- Không bao giờ lưu hay log mật khẩu dạng plain text.
- Cung cấp hàm kiểm tra hash_password, verify_password.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

# Cấu hình Argon2id theo chuẩn khuyến nghị
_hasher = PasswordHasher(
    time_cost=2,
    memory_cost=65536,
    parallelism=1,
    hash_len=32,
)

_DEV_SESSION_SECRET = "tokuyama-itam-session-secret-key-2026"

#: Thời gian sống của phiên tính từ thao tác gần nhất (BRD: tự đăng xuất sau 30 phút không thao tác).
SESSION_IDLE_SECONDS = 1800
#: Token cũ hơn ngưỡng này sẽ được cấp lại khi người dùng còn thao tác.
SESSION_RENEW_AFTER_SECONDS = 300


def load_session_secret(env: Mapping[str, str]) -> str:
    """Lấy khóa ký session cookie.

    Giá trị mặc định nằm trong mã nguồn nên ai đọc được repo cũng tự ký được
    cookie của Admin. Chỉ chấp nhận nó ở môi trường dev; production thiếu biến
    môi trường thì từ chối khởi động thay vì chạy với khóa công khai.
    """
    secret = (env.get("ITAM_SESSION_SECRET") or "").strip()
    if secret:
        return secret
    if (env.get("ITAM_ENV") or "dev").strip().lower() in ("prod", "production"):
        raise RuntimeError(
            "Thiếu biến môi trường ITAM_SESSION_SECRET. Production không được dùng khóa session mặc định."
        )
    return _DEV_SESSION_SECRET


# Khóa bí mật cho session cookie
SESSION_SECRET = load_session_secret(os.environ)
_serializer = URLSafeTimedSerializer(SESSION_SECRET, salt="itam-session-cookie")

# Hash giả định tạo sẵn để đối chiếu khi user không tồn tại, chống Timing Attack
DUMMY_PASSWORD_HASH = _hasher.hash("dummy-security-timing-protection-password")


def hash_password(password: str) -> str:
    """Băm mật khẩu người dùng bằng Argon2id."""
    if not password:
        raise ValueError("Mật khẩu không được để trống.")
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Xác minh mật khẩu đối chiếu với chuỗi băm Argon2id.

    Trả về True nếu đúng, False nếu sai hoặc chuỗi hash không hợp lệ.
    """
    if not password or not password_hash:
        return False
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError, VerificationError):
        return False


def needs_rehash(password_hash: str) -> bool:
    """Kiểm tra xem chuỗi băm có cần cập nhật thông số bảo mật mới hơn hay không."""
    try:
        return _hasher.check_needs_rehash(password_hash)
    except Exception:
        return True


def create_session_token(data: dict[str, Any]) -> str:
    """Tạo token phiên đăng nhập đã ký (signed session token)."""
    return _serializer.dumps(data)


def renew_session_token(token: str) -> str | None:
    """Cấp lại token cho phiên còn hiệu lực để hạn 30 phút tính từ thao tác gần nhất.

    Trả về None nếu token không hợp lệ/đã hết hạn, hoặc còn quá mới chưa cần cấp lại.
    """
    if not token:
        return None
    try:
        payload, issued_at = _serializer.loads(
            token, max_age=SESSION_IDLE_SECONDS, return_timestamp=True
        )
    except (BadSignature, SignatureExpired):
        return None
    if not isinstance(payload, dict):
        return None
    age = _serializer.make_signer(_serializer.salt).get_timestamp() - int(issued_at.timestamp())
    if age < SESSION_RENEW_AFTER_SECONDS:
        return None
    return _serializer.dumps(payload)


def verify_session_token(token: str, max_age_seconds: int = SESSION_IDLE_SECONDS) -> dict[str, Any] | None:
    """Giải mã và xác minh token phiên. Trả về dict dữ liệu nếu hợp lệ, None nếu hết hạn hoặc giả mạo."""
    if not token:
        return None
    try:
        payload = _serializer.loads(token, max_age=max_age_seconds)
        if isinstance(payload, dict):
            return payload
        return None
    except (BadSignature, SignatureExpired):
        return None
