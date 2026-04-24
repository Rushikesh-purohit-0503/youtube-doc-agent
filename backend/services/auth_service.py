import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt

from services.db import get_connection

JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = int(os.getenv("JWT_EXPIRY_HOURS", "720"))  # 30 days


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def create_token(user_id: str) -> str:
    payload = {
        "sub": user_id,
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRY_HOURS),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    """Raises jwt.ExpiredSignatureError or jwt.InvalidTokenError on failure."""
    return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])


def register_user(email: str, password: str) -> tuple[str, str]:
    """Returns (user_id, jwt_token). Raises ValueError if email exists."""
    user_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    pw_hash = hash_password(password)
    with get_connection() as conn:
        try:
            conn.execute(
                "INSERT INTO users (id, email, password_hash, plan, created_at) VALUES (?, ?, ?, 'free', ?)",
                (user_id, email.lower().strip(), pw_hash, now),
            )
        except Exception:
            raise ValueError("Email already registered")
    return user_id, create_token(user_id)


def login_user(email: str, password: str) -> tuple[str, str]:
    """Returns (user_id, jwt_token). Raises ValueError on bad credentials."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, password_hash FROM users WHERE email = ?",
            (email.lower().strip(),),
        ).fetchone()
    if not row or not verify_password(password, row["password_hash"]):
        raise ValueError("Invalid email or password")
    return row["id"], create_token(row["id"])


def get_user(user_id: str) -> Optional[dict]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, email, plan, created_at FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
    return dict(row) if row else None
