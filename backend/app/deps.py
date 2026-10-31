from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .db import get_db
from .models import User
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


def current_admin(request: Request, db: Session = Depends(get_db)) -> User:
    """Session (cookie) auth for admins. A user JWT is never accepted here."""
    admin_id = request.session.get("admin_id")
    admin = db.get(User, admin_id) if admin_id else None
    if admin is None or not admin.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin session required")
    return admin
