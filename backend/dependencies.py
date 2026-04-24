from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from services.auth_service import decode_token, get_user

_bearer = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
) -> dict:
    """Validates JWT and returns user dict (id, email, plan, created_at).
    Raises 401 on invalid or expired token."""
    try:
        payload = decode_token(credentials.credentials)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    user = get_user(payload["sub"])
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user
