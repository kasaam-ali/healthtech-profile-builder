"""Password hashing (bcrypt) and JWT helpers."""
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from .config import settings

ALGORITHM = "HS256"


def _pw_bytes(password: str) -> bytes:
    data = password.encode("utf-8")
    if len(data) > 72:  # defence in depth; schemas already reject with 422
        raise ValueError("password exceeds bcrypt 72-byte limit")
    return data


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_pw_bytes(password), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(_pw_bytes(password), password_hash.encode())


def _make_token(user_id: int, kind: str, lifetime: timedelta) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": str(user_id), "type": kind, "iat": now, "exp": now + lifetime}
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


def create_access_token(user_id: int) -> str:
    return _make_token(user_id, "access", timedelta(minutes=settings.access_token_minutes))


def create_refresh_token(user_id: int) -> str:
    return _make_token(user_id, "refresh", timedelta(days=settings.refresh_token_days))


def decode_token(token: str, expected_type: str) -> int | None:
    """Return user id if token is valid, unexpired and of the expected type."""
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return None
    if payload.get("type") != expected_type:
        return None
    return int(payload["sub"])
