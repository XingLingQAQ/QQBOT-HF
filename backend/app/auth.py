"""Authentication: signed session cookies + credential verification."""

import hmac
from typing import Optional

from fastapi import HTTPException, Request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from . import config

_serializer = URLSafeTimedSerializer(config.SECRET_KEY, salt="qqbot-session")


def verify_credentials(username: str, password: str) -> bool:
    """Constant-time comparison against the configured admin credentials."""
    user_ok = hmac.compare_digest(str(username), config.ADMIN_USER)
    pass_ok = hmac.compare_digest(str(password), config.ADMIN_PASS)
    return user_ok and pass_ok


def create_session(username: str) -> str:
    """Return a signed session token for the given user."""
    return _serializer.dumps({"username": username})


def _decode(token: str) -> Optional[str]:
    """Return the username if the token is valid & unexpired, else None."""
    try:
        data = _serializer.loads(token, max_age=config.SESSION_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return None
    if not isinstance(data, dict):
        return None
    username = data.get("username")
    return username if isinstance(username, str) else None


def verify_token(token: Optional[str]) -> bool:
    """Boolean token check, used by the WebSocket terminal handshake."""
    if not token:
        return False
    return _decode(token) is not None


def get_token_username(token: Optional[str]) -> Optional[str]:
    if not token:
        return None
    return _decode(token)


def require_auth(request: Request) -> str:
    """FastAPI dependency: enforce a valid session cookie, return the username."""
    token = request.cookies.get(config.SESSION_COOKIE)
    username = get_token_username(token)
    if username is None:
        raise HTTPException(status_code=401, detail="unauthorized")
    return username
