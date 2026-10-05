import hashlib
import os
import hmac
import time
from typing import Optional, Tuple
from sqlalchemy.orm import Session
from app.models.user import User
from app.config import settings

def hash_password(password: str) -> str:
    """Hash password using PBKDF2-HMAC-SHA256 with random salt."""
    salt = os.urandom(16).hex()
    key = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), 100000)
    return f"pbkdf2_sha256$100000${salt}${key.hex()}"

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password against stored PBKDF2 hash."""
    try:
        parts = hashed_password.split('$')
        if len(parts) != 4:
            return False
        iterations = int(parts[1])
        salt = parts[2]
        stored_hash = parts[3]
        key = hashlib.pbkdf2_hmac('sha256', plain_password.encode('utf-8'), salt.encode('utf-8'), iterations)
        return hmac.compare_digest(key.hex(), stored_hash)
    except Exception:
        return False

def authenticate_user(db: Session, username: str, password: str) -> Optional[User]:
    user = db.query(User).filter(User.username == username, User.is_active == True).first()
    if not user:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user

def create_session_token(user_id: int, role: str) -> str:
    """Create a tamper-proof signed session token."""
    timestamp = int(time.time())
    payload = f"{user_id}:{role}:{timestamp}"
    signature = hmac.new(settings.SECRET_KEY.encode('utf-8'), payload.encode('utf-8'), hashlib.sha256).hexdigest()
    return f"{payload}:{signature}"

def verify_session_token(token: str) -> Optional[Tuple[int, str]]:
    """Verify signed session token and enforce 30-minute inactivity limit."""
    try:
        parts = token.split(':')
        if len(parts) != 4:
            return None
        user_id = int(parts[0])
        role = parts[1]
        timestamp = int(parts[2])
        signature = parts[3]

        # Check expiration (30 minutes)
        if time.time() - timestamp > (settings.SESSION_EXPIRE_MINUTES * 60):
            return None

        payload = f"{user_id}:{role}:{timestamp}"
        expected_sig = hmac.new(settings.SECRET_KEY.encode('utf-8'), payload.encode('utf-8'), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected_sig, signature):
            return None

        return user_id, role
    except Exception:
        return None
