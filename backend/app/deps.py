from datetime import datetime, timezone
from urllib.parse import urlsplit

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .models import AdminSession, User
from .security import decode_token

bearer = HTTPBearer(auto_error=False)


def current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    """JWT auth for normal users."""
    unauthorized = HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated",
                                 headers={"WWW-Authenticate": "Bearer"})
    if creds is None:
        raise unauthorized
    user_id = decode_token(creds.credentials, "access")
    user = db.get(User, user_id) if user_id else None
    if user is None:
        raise unauthorized
    return user


def require_trusted_origin(request: Request) -> None:
    """CSRF policy for cookie-authenticated mutations: the Origin header (or, if
    absent, the Referer's origin) must be in CORS_ORIGINS. Missing both -> 403."""
    origin = request.headers.get("origin")
    if not origin:
        referer = request.headers.get("referer")
        if referer:
            parts = urlsplit(referer)
            origin = f"{parts.scheme}://{parts.netloc}"
    if not origin or origin.rstrip("/") not in settings.allowed_origins:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Untrusted or missing Origin")


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def current_admin(request: Request, db: Session = Depends(get_db)) -> User:
    """Session (cookie) auth for admins. A user JWT is never accepted here.
    The cookie holds only an opaque id; the server-side record must exist,
    be unrevoked and unexpired, and the user must still be is_admin in the DB."""
    forbidden = HTTPException(status.HTTP_403_FORBIDDEN, "Admin session required")
    sid = request.session.get("sid")
    rec = db.get(AdminSession, sid) if isinstance(sid, str) else None
    if rec is None or rec.revoked or rec.expires_at <= _now():
        raise forbidden
    admin = db.get(User, rec.user_id)
    if admin is None or not admin.is_admin:
        raise forbidden
    return admin
