"""Bảo mật mật khẩu đăng nhập bằng thuật toán Argon2id và xác thực phiên.

Quy ước từ GEMINI.md:
- Băm bằng Argon2id (thư viện argon2-cffi).
- Không bao giờ lưu hay log mật khẩu dạng plain text.
- Cung cấp hàm kiểm tra hash_password, verify_password.
"""

from __future__ import annotations

import os
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

# Khóa bí mật cho session cookie
SESSION_SECRET = os.environ.get("ITAM_SESSION_SECRET", "tokuyama-itam-session-secret-key-2026")
_serializer = URLSafeTimedSerializer(SESSION_SECRET, salt="itam-session-cookie")


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


def verify_session_token(token: str, max_age_seconds: int = 1800) -> dict[str, Any] | None:
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
