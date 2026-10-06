"""Mã hoá dữ liệu nhạy cảm bằng AES-256-GCM.

== ĐỌC KỸ TRƯỚC KHI SỬA ==

Vì sao mã hoá ở tầng ứng dụng mà không dùng pgcrypto:
  Cơ sở dữ liệu đặt trên dịch vụ cloud bên thứ ba (Neon/Supabase). Với pgcrypto,
  khoá phải nằm trong câu SQL gửi đi, nghĩa là khoá đi qua đường truyền và có
  thể lọt vào query log của nhà cung cấp. Mã hoá ở đây bảo đảm nhà cung cấp DB
  không bao giờ nhìn thấy khoá: một bản dump bị lộ chỉ là một đống byte.

Vì sao có AAD (associated data):
  AAD gắn bản mã với đúng (bảng, khoá chính, tên cột). Nếu ai đó copy
  pc_password_enc của người A sang bản ghi của người B bằng một câu UPDATE, việc
  giải mã sẽ THẤT BẠI thay vì trả ra mật khẩu sai chủ. GCM xác thực cả AAD.

Định dạng bản mã:  [1 byte key_version][12 byte nonce][ciphertext + 16 byte tag]
  key_version nằm trong chính bản mã, nên xoay khoá được từng bản ghi một,
  không cần dừng hệ thống để giải mã lại toàn bộ.

CẤM:
  - Ghi plaintext ra log, kể cả khi debug.
  - Trả plaintext từ bất kỳ endpoint nào ngoài endpoint reveal duy nhất.
  - Hardcode khoá trong code hoặc commit file chứa khoá vào Git.
"""

from __future__ import annotations

import base64
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

NONCE_BYTES = 12
KEY_BYTES = 32  # AES-256
ENV_PREFIX = "ITAM_SECRET_KEY_V"


class CryptoError(Exception):
    """Lỗi cấu hình khoá hoặc giải mã thất bại."""


class SecretBox:
    """Bộ mã hoá có hỗ trợ nhiều phiên bản khoá để xoay khoá.

    Khoá nạp từ biến môi trường ITAM_SECRET_KEY_V1, ITAM_SECRET_KEY_V2, ...
    Mỗi giá trị là 32 byte ngẫu nhiên, mã hoá base64.

    Trên máy IT, các biến này lấy từ Windows Credential Manager khi khởi động
    app, KHÔNG để trong file .env nằm trong thư mục được backup, KHÔNG commit.
    Sinh khoá mới:  python -m scripts.genkey
    """

    def __init__(self, keys: dict[int, bytes], current_version: int) -> None:
        if current_version not in keys:
            raise CryptoError(
                f"Khoá phiên bản {current_version} không có trong danh sách đã nạp"
            )
        for version, key in keys.items():
            if len(key) != KEY_BYTES:
                raise CryptoError(
                    f"Khoá V{version} dài {len(key)} byte, cần đúng {KEY_BYTES}"
                )
            if version < 1 or version > 255:
                raise CryptoError("key_version phải nằm trong 1..255")
        self._keys = keys
        self._current = current_version

    # -- nạp cấu hình ----------------------------------------------------

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> SecretBox:
        env = dict(os.environ if env is None else env)
        keys: dict[int, bytes] = {}
        for name, value in env.items():
            if not name.startswith(ENV_PREFIX):
                continue
            suffix = name[len(ENV_PREFIX) :]
            if not suffix.isdigit():
                continue
            try:
                raw = base64.b64decode(value, validate=True)
            except Exception as exc:  # noqa: BLE001
                raise CryptoError(f"{name} không phải base64 hợp lệ") from exc
            keys[int(suffix)] = raw
        if not keys:
            raise CryptoError(
                "Không tìm thấy khoá nào. Đặt ITAM_SECRET_KEY_V1 trước khi chạy app."
            )
        return cls(keys, current_version=max(keys))

    @property
    def current_version(self) -> int:
        return self._current

    # -- mã hoá / giải mã -------------------------------------------------

    @staticmethod
    def aad(table: str, record_id: int, field: str) -> bytes:
        """Gắn bản mã với đúng một ô dữ liệu."""
        return f"{table}:{record_id}:{field}".encode()

    def encrypt(self, plaintext: str, aad: bytes) -> bytes:
        if plaintext is None:
            raise CryptoError("Không mã hoá được giá trị None")
        key = self._keys[self._current]
        nonce = os.urandom(NONCE_BYTES)
        blob = AESGCM(key).encrypt(nonce, plaintext.encode("utf-8"), aad)
        return bytes([self._current]) + nonce + blob

    def decrypt(self, payload: bytes, aad: bytes) -> str:
        if not payload or len(payload) < 1 + NONCE_BYTES + 16:
            raise CryptoError("Bản mã không hợp lệ hoặc rỗng")
        version = payload[0]
        key = self._keys.get(version)
        if key is None:
            raise CryptoError(
                f"Bản ghi mã hoá bằng khoá V{version} nhưng khoá đó chưa được nạp"
            )
        nonce = payload[1 : 1 + NONCE_BYTES]
        blob = payload[1 + NONCE_BYTES :]
        try:
            return AESGCM(key).decrypt(nonce, blob, aad).decode("utf-8")
        except InvalidTag as exc:
            # Sai khoá, bản mã bị sửa, hoặc bị chép sang bản ghi khác.
            raise CryptoError("Giải mã thất bại: dữ liệu không toàn vẹn") from exc

    def rewrap(self, payload: bytes, aad: bytes) -> bytes:
        """Giải mã bằng khoá cũ rồi mã lại bằng khoá hiện tại (xoay khoá)."""
        return self.encrypt(self.decrypt(payload, aad), aad)

    @staticmethod
    def version_of(payload: bytes) -> int:
        return payload[0]


def generate_key_b64() -> str:
    """Sinh một khoá 32 byte mới, in ra dạng base64."""
    return base64.b64encode(os.urandom(KEY_BYTES)).decode()
