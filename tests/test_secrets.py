"""Test phần nhạy cảm nhất: mã hoá mật khẩu và cổng xem mật khẩu (FR-06)."""

from __future__ import annotations

import base64
import datetime as dt
import os

import pytest

from app.core.crypto import CryptoError, SecretBox, generate_key_b64
from app.core.reveal import (
    LOCKOUT_DURATION,
    MAX_FAILURES,
    TOKEN_TTL,
    RevealDenied,
    RevealGate,
    mask,
)

K1 = generate_key_b64()
K2 = generate_key_b64()
ENV = {"ITAM_SECRET_KEY_V1": K1}
ENV2 = {"ITAM_SECRET_KEY_V1": K1, "ITAM_SECRET_KEY_V2": K2}


# ===========================================================================
# Mã hoá
# ===========================================================================


def test_roundtrip():
    box = SecretBox.from_env(ENV)
    aad = SecretBox.aad("person_secrets", 42, "pc_password_enc")
    blob = box.encrypt("Tokuyama#2026", aad)
    assert box.decrypt(blob, aad) == "Tokuyama#2026"


def test_ciphertext_is_not_plaintext():
    box = SecretBox.from_env(ENV)
    aad = SecretBox.aad("person_secrets", 1, "pc_password_enc")
    blob = box.encrypt("Tokuyama#2026", aad)
    assert b"Tokuyama" not in blob


def test_same_plaintext_gives_different_ciphertext():
    """Nonce ngẫu nhiên: hai nhân viên dùng cùng mật khẩu không nhìn ra được."""
    box = SecretBox.from_env(ENV)
    aad = SecretBox.aad("person_secrets", 1, "pc_password_enc")
    assert box.encrypt("same", aad) != box.encrypt("same", aad)


def test_ciphertext_cannot_be_moved_to_another_person():
    """Chép pc_password_enc của người A sang người B phải giải mã THẤT BẠI.

    Đây là tác dụng của AAD. Không có nó, một câu UPDATE chạy tay sẽ làm người
    B hiện ra mật khẩu của người A mà không ai biết.
    """
    box = SecretBox.from_env(ENV)
    blob = box.encrypt("secret", SecretBox.aad("person_secrets", 1, "pc_password_enc"))
    with pytest.raises(CryptoError):
        box.decrypt(blob, SecretBox.aad("person_secrets", 2, "pc_password_enc"))


def test_ciphertext_cannot_be_moved_to_another_field():
    box = SecretBox.from_env(ENV)
    blob = box.encrypt("secret", SecretBox.aad("person_secrets", 1, "pc_password_enc"))
    with pytest.raises(CryptoError):
        box.decrypt(blob, SecretBox.aad("person_secrets", 1, "email_password_enc"))


def test_tampered_ciphertext_is_rejected():
    box = SecretBox.from_env(ENV)
    aad = SecretBox.aad("person_secrets", 1, "pc_password_enc")
    blob = bytearray(box.encrypt("secret", aad))
    blob[-1] ^= 0x01
    with pytest.raises(CryptoError):
        box.decrypt(bytes(blob), aad)


def test_wrong_key_cannot_decrypt():
    aad = SecretBox.aad("person_secrets", 1, "pc_password_enc")
    blob = SecretBox.from_env(ENV).encrypt("secret", aad)
    other = SecretBox.from_env({"ITAM_SECRET_KEY_V1": generate_key_b64()})
    with pytest.raises(CryptoError):
        other.decrypt(blob, aad)


def test_key_rotation_keeps_old_records_readable():
    """Xoay khoá: bản ghi cũ vẫn đọc được, bản ghi mới dùng khoá mới."""
    aad = SecretBox.aad("person_secrets", 1, "pc_password_enc")
    old_blob = SecretBox.from_env(ENV).encrypt("old-secret", aad)

    box2 = SecretBox.from_env(ENV2)
    assert box2.current_version == 2
    assert box2.decrypt(old_blob, aad) == "old-secret"
    assert SecretBox.version_of(old_blob) == 1

    new_blob = box2.rewrap(old_blob, aad)
    assert SecretBox.version_of(new_blob) == 2
    assert box2.decrypt(new_blob, aad) == "old-secret"


def test_missing_key_version_is_a_clear_error():
    aad = SecretBox.aad("person_secrets", 1, "pc_password_enc")
    blob = SecretBox.from_env(ENV2).encrypt("secret", aad)  # dùng V2
    with pytest.raises(CryptoError, match="V2"):
        SecretBox.from_env(ENV).decrypt(blob, aad)  # chỉ có V1


def test_app_refuses_to_start_without_key():
    with pytest.raises(CryptoError, match="ITAM_SECRET_KEY_V1"):
        SecretBox.from_env({})


def test_short_key_rejected():
    with pytest.raises(CryptoError):
        SecretBox.from_env(
            {"ITAM_SECRET_KEY_V1": base64.b64encode(os.urandom(16)).decode()}
        )


# ===========================================================================
# Cổng xem mật khẩu
# ===========================================================================

HASH = "argon2-hash-gia-lap"


def _verifier(password: str, password_hash: str) -> bool:
    return password == "correct-horse" and password_hash == HASH


class _Clock:
    def __init__(self) -> None:
        self.now = dt.datetime(2026, 10, 6, 9, 0, tzinfo=dt.timezone.utc)

    def __call__(self) -> dt.datetime:
        return self.now

    def advance(self, **kw) -> None:
        self.now += dt.timedelta(**kw)


def test_mask_never_leaks():
    assert mask("Tokuyama#2026") == "••••••"
    assert "Tokuyama" not in mask("Tokuyama#2026")
    assert mask(None) == ""


def test_token_required_before_reveal():
    gate = RevealGate()
    with pytest.raises(RevealDenied) as e:
        gate.check_token(1, None)
    assert e.value.reason == "no_token"


def test_correct_password_grants_token():
    gate = RevealGate()
    token = gate.authorize(1, "correct-horse", HASH, _verifier)
    gate.check_token(1, token)  # không ném lỗi


def test_wrong_password_denied():
    gate = RevealGate()
    with pytest.raises(RevealDenied) as e:
        gate.authorize(1, "sai", HASH, _verifier)
    assert e.value.reason == "bad_password"


def test_token_expires_after_two_minutes():
    clock = _Clock()
    gate = RevealGate(now=clock)
    token = gate.authorize(1, "correct-horse", HASH, _verifier)
    clock.advance(seconds=TOKEN_TTL.total_seconds() - 1)
    gate.check_token(1, token)  # còn hạn
    clock.advance(seconds=2)
    with pytest.raises(RevealDenied) as e:
        gate.check_token(1, token)
    assert e.value.reason == "token_expired"


def test_token_of_one_user_does_not_work_for_another():
    gate = RevealGate()
    token = gate.authorize(1, "correct-horse", HASH, _verifier)
    with pytest.raises(RevealDenied):
        gate.check_token(2, token)


def test_lockout_after_five_failures():
    clock = _Clock()
    gate = RevealGate(now=clock)
    for _ in range(MAX_FAILURES - 1):
        with pytest.raises(RevealDenied) as e:
            gate.authorize(1, "sai", HASH, _verifier)
        assert e.value.reason == "bad_password"

    with pytest.raises(RevealDenied) as e:
        gate.authorize(1, "sai", HASH, _verifier)
    assert e.value.reason == "locked"
    assert gate.is_locked(1)


def test_lockout_blocks_even_the_correct_password():
    """Khoá rồi thì mật khẩu đúng cũng không qua - nếu không thì khoá vô nghĩa."""
    gate = RevealGate()
    for _ in range(MAX_FAILURES):
        with pytest.raises(RevealDenied):
            gate.authorize(1, "sai", HASH, _verifier)
    with pytest.raises(RevealDenied) as e:
        gate.authorize(1, "correct-horse", HASH, _verifier)
    assert e.value.reason == "locked"


def test_lockout_expires():
    clock = _Clock()
    gate = RevealGate(now=clock)
    for _ in range(MAX_FAILURES):
        with pytest.raises(RevealDenied):
            gate.authorize(1, "sai", HASH, _verifier)
    clock.advance(seconds=LOCKOUT_DURATION.total_seconds() + 1)
    assert not gate.is_locked(1)
    gate.authorize(1, "correct-horse", HASH, _verifier)


def test_lockout_is_per_user():
    gate = RevealGate()
    for _ in range(MAX_FAILURES):
        with pytest.raises(RevealDenied):
            gate.authorize(1, "sai", HASH, _verifier)
    gate.authorize(2, "correct-horse", HASH, _verifier)  # người khác không bị ảnh hưởng


def test_revoke_on_logout():
    gate = RevealGate()
    token = gate.authorize(1, "correct-horse", HASH, _verifier)
    gate.revoke(1)
    with pytest.raises(RevealDenied):
        gate.check_token(1, token)
